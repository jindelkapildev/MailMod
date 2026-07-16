import os
import re
import asyncio
import discord
from discord.ext import commands, tasks
from supabase import create_client, Client

# Configure your target Discord Channel ID where new mails should automatically post
NOTIFY_CHANNEL_ID = 1521142308966371332  # 👈 Replace this with your actual Channel ID

class MailLinkButton(discord.ui.View):
    """Adds a dynamic link button below the embed targeting your dashboard."""
    def __init__(self, record_id):
        super().__init__()
        dashboard_url = f"https://mail.admin.com/view?id={record_id}"
        self.add_item(discord.ui.Button(
            label="View Complete Mail", 
            url=dashboard_url, 
            style=discord.ButtonStyle.link,
            emoji="🔗"
        ))

class InboxCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.last_checked_id = None  # Tracks the newest processed mail ID
        
        # Initialize Supabase Client
        supabase_url = os.getenv("SUPABASE_URL")
        supabase_key = os.getenv("SUPABASE_KEY")
        
        if not supabase_url or not supabase_key:
            print("⚠️ [Inbox Cog] Missing Supabase environment variables!")
            self.supabase: Client = None
        else:
            self.supabase: Client = create_client(supabase_url, supabase_key)
            
        # Start the background real-time listener loop
        self.auto_mail_checker.start()

    def cog_unload(self):
        self.auto_mail_checker.cancel()

    def parse_sender(self, raw_sender):
        """Splits raw header formats like '\"Supercell\" <noreply@id.supercell.com>' into Name and Mail cleanly."""
        if not raw_sender:
            return "Unknown Sender", "info@mail.admin.com"
        
        # Match pattern for "Name" <email@domain.com>
        match = re.match(r'(?:"?([^"]*)"?\s+)?<([^>]+)>', raw_sender)
        if match:
            name = match.group(1) or "Sender's Name"
            email = match.group(2)
            return name.strip(), email.strip()
        
        # Fallback if it's just a raw email or name without angle brackets
        if "@" in raw_sender:
            return "Sender's Name", raw_sender.strip()
        
        return raw_sender.strip(), "info@mail.admin.com"

    def create_mail_embed(self, record, current_index, total_count):
        """Builds an optimized, premium layout matching your template with conditional OTP fields."""
        raw_sender = record.get("sender") or ""
        sender_name, sender_mail = self.parse_sender(raw_sender)
        
        recipient = record.get("recipient") or record.get("to") or "beta@mail.admin.com"
        subject = record.get("subject") or "(No Subject)"
        body = record.get("body_text") or record.get("raw_body") or "No content."
        
        # Scanning and isolating an OTP code dynamically
        otp_match = re.search(r'\b\d{4,8}\b', body) or re.search(r'\b\d{4,8}\b', subject)
        otp_code = otp_match.group(0) if otp_match else None

        if len(body) > 1000:
            body = body[:997] + "..."

        embed = discord.Embed(
            title=f"✨ **Todays Mail** : {record.get('created_at', '2026-06-29')[:10]} ✨",
            color=10052095
        )
        
        icon_url = "https://media.discordapp.net/attachments/1519257143721590864/1519324369963188346/download.png"
        embed.set_thumbnail(url=icon_url)

        embed.add_field(name="From", value=sender_name, inline=True)
        embed.add_field(name="Sender Mail", value=sender_mail, inline=True)
        embed.add_field(name="To", value=recipient, inline=False)
        
        # Conditional Logic: Only append OTP area if a pattern target is matched
        if otp_code:
            embed.add_field(name="OTP (Tap to Copy)", value=f"`{otp_code}`", inline=False)

        embed.add_field(name="Content", value=body, inline=False)
        
        attachments = record.get("attachments", [])
        if attachments and len(attachments) > 0:
            attach_str = ""
            for i, att in enumerate(attachments[:2]):
                emoji = "<:sub_entry_one:1519326682891288666>" if i == 0 else "<:sub_entry_two:1519326714679918632>"
                url = att.get("url", "https://mail.admin.com")
                name = att.get("name", f"Attachment {i+1}")
                attach_str += f"{emoji} **{name}** : **[Click Here ]({url})**\n"
            embed.add_field(name="Attachments :", value=attach_str, inline=False)

        embed.set_footer(
            text=f"✧ Mail12599 ✧ Email {current_index + 1} of {total_count}",
            icon_url=icon_url
        )
        return embed

    @tasks.loop(seconds=5.0)
    async def auto_mail_checker(self):
        """Background worker that checks Supabase every 5 seconds for new emails and prints them automatically."""
        if not self.supabase or not self.bot.is_ready():
            return

        try:
            # Query the single absolute newest entry from the database
            response = self.supabase.table("inbox").select("*").order("created_at", desc=True).limit(1).execute()
            if not response.data:
                return

            latest_record = response.data[0]
            record_id = latest_record.get("id")

            # Initialization skip: avoids spamming old historical records when the bot first boots up
            if self.last_checked_id is None:
                self.last_checked_id = record_id
                return

            # If the newest database ID is different from our tracker, we received a new mail!
            if record_id != self.last_checked_id:
                self.last_checked_id = record_id

                channel = self.bot.get_channel(NOTIFY_CHANNEL_ID)
                if channel:
                    embed = self.create_mail_embed(latest_record, 0, 1)
                    view = MailLinkButton(record_id=record_id)
                    
                    # Target ping string can go here (e.g. content="@role")
                    await channel.send(
                        content=f"**Subject : {latest_record.get('subject', 'No Subject')}**", 
                        embed=embed, 
                        view=view
                    )
        except Exception as e:
            print(f"❌ Error in auto mail checker loop: {e}")

    @auto_mail_checker.before_loop
    async def before_checker(self):
        await self.bot.wait_until_ready()

    @commands.command(name="latest_mail", aliases=["inbox"])
    async def get_latest_mail(self, ctx):
        """Fetches the absolute newest entry manually from the Supabase inbox table."""
        if not self.supabase:
            return await ctx.send("❌ Supabase client is not configured properly.")

        async with ctx.typing():
            try:
                response = self.supabase.table("inbox").select("*").order("created_at", desc=True).limit(1).execute()
                if not response.data:
                    return await ctx.send("📭 The inbox database is currently empty.")
                
                record = response.data[0]
                embed = self.create_mail_embed(record, 0, 1)
                view = MailLinkButton(record_id=record.get("id", "0"))
                
                await ctx.send(content=f"**Subject : {record.get('subject', 'Test with data')}**", embed=embed, view=view)
            except Exception as e:
                print(f"❌ Error: {e}")
                await ctx.send("⚠️ An error occurred while fetching data.")

    @commands.command(name="old_mails", aliases=["history", "mails"])
    async def get_old_mails(self, ctx):
        """Fetches historical emails and allows browsing via reaction buttons."""
        if not self.supabase:
            return await ctx.send("❌ Supabase client is not configured properly.")

        async with ctx.typing():
            try:
                response = self.supabase.table("inbox").select("*").order("created_at", desc=True).limit(20).execute()
                records = response.data

                if not records:
                    return await ctx.send("📭 No historical emails found in the database.")
                
                if len(records) == 1:
                    embed = self.create_mail_embed(records[0], 0, 1)
                    view = MailLinkButton(record_id=records[0].get("id", "0"))
                    await ctx.send(content=f"**Subject : {records[0].get('subject')}**", embed=embed, view=view)
                    return

            except Exception as e:
                print(f"❌ Error: {e}")
                return await ctx.send("⚠️ An error occurred while fetching history.")

        current_page = 0
        total_pages = len(records)
        
        embed = self.create_mail_embed(records[current_page], current_page, total_pages)
        view = MailLinkButton(record_id=records[current_page].get("id", "0"))
        message = await ctx.send(content=f"**Subject : {records[current_page].get('subject')}**", embed=embed, view=view)

        await message.add_reaction("◀️")
        await message.add_reaction("▶️")

        def check(reaction, user):
            return user == ctx.author and str(reaction.emoji) in ["◀️", "▶️"] and reaction.message.id == message.id

        while True:
            try:
                reaction, user = await self.bot.wait_for("reaction_add", timeout=120.0, check=check)

                if str(reaction.emoji) == "▶️" and current_page < total_pages - 1:
                    current_page += 1
                elif str(reaction.emoji) == "◀️" and current_page > 0:
                    current_page -= 1
                else:
                    await message.remove_reaction(reaction.emoji, user)
                    continue

                new_embed = self.create_mail_embed(records[current_page], current_page, total_pages)
                new_view = MailLinkButton(record_id=records[current_page].get("id", "0"))
                await message.edit(content=f"**Subject : {records[current_page].get('subject')}**", embed=new_embed, view=new_view)
                await message.remove_reaction(reaction.emoji, user)

            except asyncio.TimeoutError:
                try:
                    await message.clear_reactions()
                except discord.Forbidden:
                    pass
                break

async def setup(bot):
    await bot.add_cog(InboxCog(bot))
