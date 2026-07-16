import os
import re
import asyncio
import discord
from discord.ext import commands

# --- CONFIGURATION ---
NOTIFY_CHANNEL_ID = 1527301001651028199  # 👈 Keep your channel ID here

# Staff roles silently added to every new thread (matches your secure role IDs setup)
ROLES_TO_ADD_IDS = [
]

def clean_recipient_name(raw_recipient):
    """Formats raw emails into standard thread names (admin - example@domain.com)."""
    if not raw_recipient:
        email_addr = "unknown-recipient"
    else:
        match = re.search(r'<([^>]+)>', raw_recipient)
        if match:
            email_addr = match.group(1).strip().lower()
        else:
            email_addr = raw_recipient.strip().lower()
    return f"admin - {email_addr}"


# --- MODAL: GET MAIL ---
class GetMailModal(discord.ui.Modal):
    def __init__(self):
        super().__init__(title="Configure New Inbox")
        self.email_input = discord.ui.TextInput(
            label="What is your target email address?",
            placeholder="e.g. info@yourdomain.com",
            style=discord.TextStyle.short,
            required=True,
            max_length=100
        )
        self.add_item(self.email_input)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        raw_email = self.email_input.value
        thread_name = clean_recipient_name(raw_email)
        channel = interaction.guild.get_channel(NOTIFY_CHANNEL_ID)

        if not channel:
            return await interaction.followup.send("❌ Target notification channel not found.", ephemeral=True)

        target_thread = None

        # 1. Look for existing thread (Active)
        for thread in channel.threads:
            if thread.name.lower() == thread_name.lower():
                target_thread = thread
                break

        # 2. Look for existing thread (Archived)
        if not target_thread:
            try:
                async for thread in channel.archived_threads(limit=100):
                    if thread.name.lower() == thread_name.lower():
                        await thread.edit(archived=False)
                        target_thread = thread
                        break
            except Exception as e:
                print(f"⚠️ Error checking archived threads: {e}")

        # 3. Create a new thread if it doesn't exist
        is_new = False
        if not target_thread:
            is_new = True
            target_thread = await channel.create_thread(
                name=thread_name,
                type=discord.ChannelType.public_thread,
                auto_archive_duration=1440
            )

        # 4. Silently add staff roles
        guild = interaction.guild
        added_members = {interaction.user.id}  # Make sure the creator isn't treated as a duplicate
        for role_id in ROLES_TO_ADD_IDS:
            role = guild.get_role(role_id)
            if role:
                for member in role.members:
                    if member.id not in added_members and not member.bot:
                        try:
                            await target_thread.add_user(member)
                            added_members.add(member.id)
                        except Exception as e:
                            print(f"⚠️ Staff {member.name} could not be added: {e}")

        # 5. Add the user who requested the inbox
        try:
            await target_thread.add_user(interaction.user)
        except Exception as e:
            print(f"⚠️ User could not be added: {e}")

        # Send welcome message if thread is brand new
        if is_new:
            await target_thread.send(
                f"📬 **Mailbox Initialized**\n"
                f"Welcome to your dedicated mail thread {interaction.user.mention}!\n"
                f"Any incoming emails addressing `{raw_email}` will route directly into this thread."
            )

        await interaction.followup.send(
            f"✅ **Inbox Created/Matched!**\n"
            f"You have been added to: {target_thread.mention}", 
            ephemeral=True
        )


# --- MODAL: FIND MAIL ---
class FindMailModal(discord.ui.Modal):
    def __init__(self):
        super().__init__(title="Find Existing Inbox")
        self.email_input = discord.ui.TextInput(
            label="What is your email address?",
            placeholder="e.g. info@yourdomain.com",
            style=discord.TextStyle.short,
            required=True,
            max_length=100
        )
        self.add_item(self.email_input)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        raw_email = self.email_input.value
        thread_name = clean_recipient_name(raw_email)
        channel = interaction.guild.get_channel(NOTIFY_CHANNEL_ID)

        if not channel:
            return await interaction.followup.send("❌ Target notification channel not found.", ephemeral=True)

        target_thread = None

        # 1. Check Active Threads
        for thread in channel.threads:
            if thread.name.lower() == thread_name.lower():
                target_thread = thread
                break

        # 2. Check Archived Threads
        if not target_thread:
            try:
                async for thread in channel.archived_threads(limit=100):
                    if thread.name.lower() == thread_name.lower():
                        await thread.edit(archived=False)
                        target_thread = thread
                        break
            except Exception as e:
                print(f"⚠️ Error searching archived threads: {e}")

        if not target_thread:
            return await interaction.followup.send(
                f"❌ **No Mailbox Found** for `{raw_email}`.\n"
                f"Please select **Get Mail** on the panel to create it first!",
                ephemeral=True
            )

        # 3. Add user to the thread
        try:
            await target_thread.add_user(interaction.user)
        except Exception as e:
            print(f"⚠️ Could not add user to thread: {e}")

        # 4. Bump the thread so it pops to the top, then silently delete the bump
        try:
            bump_msg = await target_thread.send(f"👋 {interaction.user.mention} has restored this thread!")
            await asyncio.sleep(1.5)  # Let Discord register the thread bump
            await bump_msg.delete()   # Instantly delete to keep the inbox clean
        except Exception as e:
            print(f"⚠️ Failed to send/delete bump message: {e}")

        await interaction.followup.send(
            f"✨ **Mailbox Found!**\n"
            f"We've restored {target_thread.mention} on your sidebar.",
            ephemeral=True
        )


# --- INTERACTIVE PANEL VIEW ---
class PanelControlView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None) # Persistent View so buttons never break on bot restarts

    @discord.ui.button(label="Get Mail", style=discord.ButtonStyle.success, custom_id="get_mail_btn", emoji="📬")
    async def get_mail(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(GetMailModal())

    @discord.ui.button(label="Find Mail", style=discord.ButtonStyle.primary, custom_id="find_mail_btn", emoji="🔍")
    async def find_mail(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(FindMailModal())


# --- COG SETUP ---
class PanelCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_ready(self):
        # Register the persistent view so the buttons work even if the bot restarts
        self.bot.add_view(PanelControlView())
        print("✅ [Panel Cog] Persistent buttons registered.")

    @commands.command(name="setup_panel")
    @commands.has_permissions(administrator=True)
    async def setup_panel(self, ctx):
        """Sends the static dashboard control panel into the notification channel."""
        target_channel = self.bot.get_channel(NOTIFY_CHANNEL_ID)
        if not target_channel:
            return await ctx.send("❌ Error: Target notification channel is invalid or offline.")

        embed = discord.Embed(
            title="📥 **Personal Secure Mailbox Hub** 📥",
            description=(
                "Welcome to the mail control dashboard! Use the interactive systems below "
                "to easily allocate secure workspace addresses.\n\n"
                "🔹 **Get Mail**\n"
                "Instantly reserve a custom mailbox thread. This will establish a private workspace thread "
                "accessible only by you and the administration staff.\n\n"
                "🔹 **Find Mail**\n"
                "Lost your thread or accidentally removed it? Enter your email address to instantly "
                "unarchive, fetch, and restore the thread on your sidebar."
            ),
            color=10052095
        )
        embed.set_thumbnail(url="https://media.discordapp.net/attachments/1519257143721590864/1519324369963188346/download.png")
        embed.set_footer(text="✧ Secure Mail System ✧ Persistent Thread Utility")

        view = PanelControlView()
        await target_channel.send(embed=embed, view=view)
        await ctx.send(f"✅ Panel deployed successfully inside {target_channel.mention}!")

async def setup(bot):
    await bot.add_cog(PanelCog(bot))
