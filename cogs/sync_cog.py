import os
import json
import asyncio
import aiohttp
import discord
from discord.ext import commands
from supabase import create_client, Client

class SyncCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        
        # Initialize Supabase Client
        self.supabase_url = os.getenv("SUPABASE_URL")
        self.supabase_key = os.getenv("SUPABASE_KEY")
        if not self.supabase_url or not self.supabase_key:
            print("⚠️ [Sync Cog] Missing Supabase environment variables!")
            self.supabase = None
        else:
            self.supabase: Client = create_client(self.supabase_url, self.supabase_key)
        
        # Cloudflare D1 configuration[cite: 1]
        self.cf_account_id = os.getenv("CLOUDFLARE_ACCOUNT_ID")[cite: 1]
        self.cf_database_id = os.getenv("CLOUDFLARE_DATABASE_ID")[cite: 1]
        self.cf_api_token = os.getenv("CLOUDFLARE_API_TOKEN")[cite: 1]
        
        # Setup the D1 REST API Endpoint URL
        if self.cf_account_id and self.cf_database_id:
            self.d1_api_url = f"https://api.cloudflare.com/client/v4/accounts/{self.cf_account_id}/d1/database/{self.cf_database_id}/query"[cite: 1]
        else:
            self.d1_api_url = None
            print("⚠️ [Sync Cog] Missing Cloudflare D1 environment variables!")

    async def execute_d1_query(self, sql: str, params: list):
        """Sends a SQL query and parameter list to Cloudflare D1's REST API endpoint."""
        if not self.cf_api_token or not self.d1_api_url:
            raise ValueError("Cloudflare configuration is incomplete.")

        headers = {
            "Authorization": f"Bearer {self.cf_api_token}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "sql": sql,
            "params": params
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(self.d1_api_url, headers=headers, json=payload) as response:
                if response.status != 200:
                    text = await response.text()
                    raise Exception(f"Cloudflare API returned status {response.status}: {text}")
                
                result = await response.json()
                if not result.get("success"):
                    raise Exception(f"Cloudflare Query failed: {result.get('errors')}")
                return result

    @commands.command(name="sync")
    @commands.has_permissions(administrator=True)
    async def sync_database(self, ctx):
        """
        Safely migrates entries one by one:
        Copies from Supabase -> Pastes to Cloudflare D1 -> Deletes from Supabase.
        """
        if not self.supabase:
            return await ctx.send("❌ Supabase is not configured.")
        if not self.d1_api_url:
            return await ctx.send("❌ Cloudflare D1 is not configured.")

        status_msg = await ctx.send("🔄 **Sync Initiated.** Starting secure one-by-one migration...")
        total_moved = 0
        
        # We fetch in small batches from Supabase to reduce network calls,
        # but we still process and delete them ONE-BY-ONE sequentially.
        batch_size = 50 
        has_more = True

        async with ctx.typing():
            try:
                while has_more:
                    # Fetch oldest records first so we migrate in chronological order
                    response = (
                        self.supabase.table("inbox")
                        .select("*")
                        .order("created_at", desc=False)
                        .limit(batch_size)
                        .execute()
                    )
                    
                    records = response.data
                    if not records:
                        has_more = False
                        break

                    for record in records:
                        record_id = record.get("id")
                        attachments_json = json.dumps(record.get("attachments", []))
                        
                        insert_sql = """
                        INSERT OR IGNORE INTO inbox (
                            id, created_at, sender, recipient, subject, 
                            body_text, body_html, raw_body, time, attachments, uid
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                        """
                        
                        params = [
                            record_id,
                            record.get("created_at"),
                            record.get("sender"),
                            record.get("recipient") or record.get("to"),
                            record.get("subject"),
                            record.get("body_text"),
                            record.get("body_html"),
                            record.get("raw_body"),
                            record.get("time"),
                            attachments_json,
                            record.get("uid")
                        ]
                        
                        try:
                            # 1. COPY: Write to Cloudflare D1
                            await self.execute_d1_query(insert_sql, params)
                            
                            # 2. DELETE: Remove from Supabase ONLY after D1 write is confirmed successful
                            self.supabase.table("inbox").delete().eq("id", record_id).execute()
                            
                            total_moved += 1
                            
                            # Edit message occasionally to show progress without spamming Discord's API rate limits
                            if total_moved % 5 == 0 or total_moved == 1:
                                await status_msg.edit(content=f"⚙️ **Migrating...** Safely moved `{total_moved}` records to Cloudflare.")
                            
                            # Extremely brief pause to keep things smooth
                            await asyncio.sleep(0.1)
                            
                        except Exception as single_err:
                            # If a single row fails to write, we stop the sync immediately.
                            # The row remains safe in Supabase.
                            print(f"❌ Failed to migrate record ID {record_id}: {single_err}")
                            await ctx.send(f"⚠️ **Sync paused mid-process due to an error at ID {record_id}:**\n`{str(single_err)}`")
                            has_more = False
                            break

                # Final Status Update
                if total_moved > 0:
                    await status_msg.edit(content=f"✅ **Storage Cleaned!**\nSuccessfully moved and cleared `{total_moved}` mail records from Supabase into Cloudflare D1.")
                else:
                    await status_msg.edit(content="📭 **Sync complete.** Supabase is already clean—no records found to migrate.")

            except Exception as e:
                print(f"❌ Global Sync Error: {e}")
                await ctx.send(f"⚠️ **Sync aborted due to a global error:**\n`{str(e)}`")

async def setup(bot):
    await bot.add_cog(SyncCog(bot))
