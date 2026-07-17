import os
import re
import asyncio
import discord
import aiohttp
from discord.ext import commands, tasks
from supabase import create_client, Client

NOTIFY_CHANNEL_ID = 1527301001651028199  
ROLES_TO_ADD_IDS = [1519709968847081675]

class MailLinkButton(discord.ui.View):
    """Adds a dynamic link button below the embed targeting your dashboard."""
    def __init__(self, record_uid):  # Changed parameter to match UUID column name
        super().__init__()
        base_url = os.getenv("DASHBOARD_URL", "https://mailmod.onrender.com")
        # Route using the secure, unguessable UUID string (uid)
        dashboard_url = f"{base_url.rstrip('/')}/view?id={record_uid}"
        
        self.add_item(discord.ui.Button(
            label="Read Full Mail", 
            url=dashboard_url, 
            style=discord.ButtonStyle.link,
            emoji="🔗"
        ))

class InboxCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.last_checked_uid = None  # Tracks by UUID instead of numerical ID
        
        # Initialize Supabase Client
        supabase_url = os.getenv("SUPABASE_URL")
        supabase_key = os.getenv("SUPABASE_KEY")
        self.supabase = create_client(supabase_url, supabase_key) if supabase_url and supabase_key else None
            
        # Cloudflare D1 Credentials
        self.cf_account_id = os.getenv("CLOUDFLARE_ACCOUNT_ID")
        self.cf_database_id = os.getenv("CLOUDFLARE_DATABASE_ID")
        self.cf_api_token = os.getenv("CLOUDFLARE_API_TOKEN")
        
        self.auto_mail_checker.start()

    def cog_unload(self):
        self.auto_mail_checker.cancel()

    async def query_cloudflare_d1(self, sql_query, params=[]):
        """Helper to query Cloudflare D1 via REST API."""
        if not all([self.cf_account_id, self.cf_database_id, self.cf_api_token]):
            return None
        url = f"https://api.cloudflare.com/client/v4/accounts/{self.cf_account_id}/d1/database/{self.cf_database_id}/query"
        headers = {"Authorization": f"Bearer {self.cf_api_token}", "Content-Type": "application/json"}
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=headers, json={"sql": sql_query, "params": params}) as response:
                    if response.status == 200:
                        res_json = await response.json()
                        if res_json.get("success") and res_json["result"][0]["results"]:
                            return res_json["result"][0]["results"]
        except Exception as e:
            print(f"⚠️ Cloudflare D1 Error: {e}")
        return None

    async def fetch_latest_record(self):
        """Checks Supabase first for the latest mail, falls back to Cloudflare D1."""
        if self.supabase:
            try:
                response = self.supabase.table("inbox").select("*").order("created_at", desc=True).limit(1).execute()
                if response.data:
                    return response.data[0]
            except Exception as e:
                print(f"⚠️ Supabase fetch error: {e}")

        # Cloudflare D1 Fallback
        cf_rows = await self.query_cloudflare_d1("SELECT * FROM inbox ORDER BY created_at DESC LIMIT 1")
        if cf_rows:
            return cf_rows[0]
        return None

    def parse_sender(self, raw_sender):
        if not raw_sender: return "Unknown Sender", "info@mail.admin.com"
        match = re.match(r'(?:"?([^"]*)"?\s+)?<([^>]+)>', raw_sender)
        if match: return match.group(1) or "Sender's Name", match.group(2).strip()
        return ("Sender's Name", raw_sender.strip()) if "@" in raw_sender else (raw_sender.strip(), "info@mail.admin.com")

    def clean_recipient_name(self, raw_recipient):
        if not raw_recipient: email_addr = "unknown-recipient"
        else:
            match = re.search(r'<([^>]+)>', raw_recipient)
            email_addr = match.group(1).strip().lower() if match else raw_recipient.strip().lower()
        return f"admin - {email_addr}"

    async def get_or_create_mail_thread(self, channel, thread_name):
        for thread in channel.threads:
            if thread.name.lower() == thread_name.lower(): return thread
        try:
            async for thread in channel.archived_threads(limit=100):
                if thread.name.lower() == thread_name.lower():
                    await thread.edit(archived=False)
                    return thread
        except Exception as e: print(f"⚠️ Thread scan error: {e}")

        new_thread = await channel.create_thread(name=thread_name, type=discord.ChannelType.public_thread, auto_archive_duration=1440)
        guild = channel.guild
        added_members = set()
        for role_id in ROLES_TO_ADD_IDS:
            role = guild.get_role(role_id)
            if role:
                for member in role.members:
                    if member.id not in added_members and not member.bot:
                        try:
                            await new_thread.add_user(member)
                            added_members.add(member.id)
                        except Exception as e: print(f"⚠️ Thread join error: {e}")
        return new_thread

    def create_mail_embed(self, record, current_index, total_count):
        raw_sender = record.get("sender") or ""
        sender_name, sender_mail = self.parse_sender(raw_sender)
        recipient = record.get("recipient") or record.get("to") or "beta@mail.admin.com"
        subject = record.get("subject") or "(No Subject)"
        body = record.get("body_text") or record.get("raw_body") or ""
        
        otp_match = re.search(r'\b\d{4,8}\b', body) or re.search(r'\b\d{4,8}\b', subject)
        embed = discord.Embed(title="✨ **New Mail Received** ✨", color=10052095)
        embed.set_thumbnail(url="https://media.discordapp.net/attachments/1519257143721590864/1519324369963188346/download.png")

        embed.add_field(name="From", value=sender_name, inline=True)
        embed.add_field(name="Sender Mail", value=sender_mail, inline=True)
        embed.add_field(name="To", value=recipient, inline=False)
        embed.add_field(name="Subject", value=f"**{subject}**", inline=False)
        
        if otp_match:
            embed.add_field(name="OTP (Tap to Copy)", value=f"`{otp_match.group(0)}`", inline=False)
            
        embed.add_field(name="Content", value="📝 *The message content is too long for Discord. Click the button below to read the complete mail securely.*", inline=False)
        
        # Safe JSON attachments parsing
        import json
        attachments = record.get("attachments", "[]")
        if isinstance(attachments, str):
            try: attachments = json.loads(attachments)
            except: attachments = []
            
        if attachments:
            attach_str = ""
            for i, att in enumerate(attachments[:2]):
                emoji = "<:sub_entry_one:1519326682891288666>" if i == 0 else "<:sub_entry_two:1519326714679918632>"
                attach_str += f"{emoji} **{att.get('name', f'Attachment {i+1}')}** : **[Click Here]({att.get('url', '#')})**\n"
            embed.add_field(name="Attachments :", value=attach_str, inline=False)

        embed.set_footer(text=f"✧ Mail System ✧ Email {current_index + 1} of {total_count}", icon_url=embed.thumbnail.url)
        return embed

    @tasks.loop(seconds=5.0)
    async def auto_mail_checker(self):
        if not self.bot.is_ready(): return
        try:
            latest_record = await self.fetch_latest_record()
            if not latest_record: return

            record_uid = latest_record.get("uid")  # Fetch unique UUID field string

            if self.last_checked_uid is None:
                self.last_checked_uid = record_uid
                return

            if record_uid != self.last_checked_uid:
                self.last_checked_uid = record_uid
                channel = self.bot.get_channel(NOTIFY_CHANNEL_ID)
                if channel:
                    thread_name = self.clean_recipient_name(latest_record.get("recipient") or latest_record.get("to") or "")
                    target_thread = await self.get_or_create_mail_thread(channel, thread_name)
                    
                    embed = self.create_mail_embed(latest_record, 0, 1)
                    view = MailLinkButton(record_uid=record_uid)
                    await target_thread.send(embed=embed, view=view)
        except Exception as e:
            print(f"❌ Error in auto mail checker loop: {e}")

    @auto_mail_checker.before_loop
    async def before_checker(self): await self.bot.wait_until_ready()

    @commands.command(name="latest_mail", aliases=["inbox"])
    async def get_latest_mail(self, ctx):
        async with ctx.typing():
            try:
                record = await self.fetch_latest_record()
                if not record: return await ctx.send("📭 The inbox database is currently empty.")
                
                thread_name = self.clean_recipient_name(record.get("recipient") or record.get("to") or "")
                target_thread = await self.get_or_create_mail_thread(ctx.channel, thread_name)

                embed = self.create_mail_embed(record, 0, 1)
                view = MailLinkButton(record_uid=record.get("uid"))
                await target_thread.send(embed=embed, view=view)
                await ctx.send(f"✅ Routed latest email to thread: {target_thread.mention}")
            except Exception as e: await ctx.send("⚠️ An error occurred while fetching data.")

    @commands.command(name="old_mails", aliases=["history", "mails"])
    async def get_old_mails(self, ctx):
        async with ctx.typing():
            try:
                records = []
                if self.supabase:
                    res = self.supabase.table("inbox").select("*").order("created_at", desc=True).limit(20).execute()
                    records = res.data
                if not records:
                    cf_rows = await self.query_cloudflare_d1("SELECT * FROM inbox ORDER BY created_at DESC LIMIT 20")
                    records = cf_rows or []

                if not records: return await ctx.send("📭 No historical emails found.")
            except Exception as e: return await ctx.send("⚠️ An error occurred while fetching history.")

        current_page = 0
        total_pages = len(records)
        
        embed = self.create_mail_embed(records[current_page], current_page, total_pages)
        view = MailLinkButton(record_uid=records[current_page].get("uid"))
        message = await ctx.send(embed=embed, view=view)
        await message.add_reaction("◀️"); await message.add_reaction("▶️")

        def check(reaction, user): return user == ctx.author and str(reaction.emoji) in ["◀️", "▶️"] and reaction.message.id == message.id

        while True:
            try:
                reaction, user = await self.bot.wait_for("reaction_add", timeout=120.0, check=check)
                if str(reaction.emoji) == "▶️" and current_page < total_pages - 1: current_page += 1
                elif str(reaction.emoji) == "◀️" and current_page > 0: current_page -= 1
                else:
                    await message.remove_reaction(reaction.emoji, user); continue

                new_embed = self.create_mail_embed(records[current_page], current_page, total_pages)
                new_view = MailLinkButton(record_uid=records[current_page].get("uid"))
                await message.edit(embed=new_embed, view=new_view)
                await message.remove_reaction(reaction.emoji, user)
            except asyncio.TimeoutError:
                try: await message.clear_reactions()
                except: pass
                break

async def setup(bot): await bot.add_cog(InboxCog(bot))
