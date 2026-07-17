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
            self.d1_api_url = f"https://api.cloudflare.com/client/v4/accounts/{self.cf_account_id}/d1/database/{self.cf_database_id}/query"
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
    @commands.has_permissions(administrator=True) # Recommended safety net
    async def sync_database(self, ctx):
        """Manually forces a step-by-step batch migration from Supabase to Cloudflare D1."""
        if not self.supabase:
            return await ctx.send("❌ Supabase is not configured.")
        if not self.d1_api_url:
            return await ctx.send("❌ Cloudflare D1 is not configured.")

        # 1. Look for a tracking column like 'is_synced'. 
        # Note: If you do not have 'is_synced' in Supabase, make sure to add it 
        # to your 'inbox' table as a boolean (DEFAULT false).
        
        status_msg = await ctx.send("🔄 **Sync Initiated.** Checking database for unsynced entries...")
        total_synced = 0
        batch_size = 100
        has_more = True

        async with ctx.typing():
            try:
                while has_more:
                    # Fetch next batch of unsynced rows from Supabase
                    response = (
                        self.supabase.table("inbox")
                        .select("*")
                        .eq("is_synced", False)
                        .limit(batch_size)
                        .execute()
                    )
                    
                    records = response.data
                    if not records:
                        has_more = False
                        break

                    # Process each record to build a bulk SQL script or run sequential insertions.
                    # Since D1 REST API allows parameterized execution, we construct parameterized inserts.
                    for record in records:
                        # Convert attachments list to text for SQLite storage
                        attachments_json = json.dumps(record.get("attachments", []))
                        
                        insert_sql = """
                        INSERT OR IGNORE INTO inbox (
                            id, created_at, sender, recipient, subject, 
                            body_text, body_html, raw_body, time, attachments, uid
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
                        """
                        
                        params = [
                            record.get("id"),
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
                        
                        # Executing query over Cloudflare HTTP interface
                        await self.execute_d1_query(insert_sql, params)

                    # Update Supabase for this specific batch so we don't query them again
                    ids_to_update = [r.get("id") for r in records]
                    self.supabase.table("inbox").update({"is_synced": True}).in_("id", ids_to_update).execute()

                    total_synced += len(records)
                    await status_msg.edit(content=f"⚙️ **Syncing...** Successfully processed `{total_synced}` records so far.")
                    
                    # Prevent rapid hammering of both databases
                    await asyncio.sleep(1.0)

                # Final Success Message
                if total_synced > 0:
                    await status_msg.edit(content=f"✅ **Sync completed successfully!**\nMoved `{total_synced}` mail records over to Cloudflare D1.")
                else:
                    await status_msg.edit(content="📭 **Sync completed.** There were no new unsynced entries to transfer.")

            except Exception as e:
                print(f"❌ Error during sync execution: {e}")
                await ctx.send(f"⚠️ **Sync aborted due to an error:**\n`{str(e)}`")

async def setup(bot):
    await bot.add_cog(SyncCog(bot))
