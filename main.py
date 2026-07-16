import os
import asyncio
from dotenv import load_dotenv
# Directly import the working bot instance from your unchanged war_tracker file
from bot_instance import bot
# Import the web server task from your new page.py file
from page import run_web_server
import discord
bot.intents.members = True

load_dotenv()
DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")

async def dynamic_setup_hook():
    """Scans the cogs folder for any new functions we add in the future."""
    print("-----------------------------------------------------")
    print("[System] Scanning 'cogs' folder for future functions...")
    
    if os.path.exists("./cogs"):
        for filename in os.listdir("./cogs"):
            if filename.endswith(".py") and not filename.startswith("__"):
                cog_name = f"cogs.{filename[:-3]}"
                try:
                    await bot.load_extension(cog_name)
                    print(f"📦 Successfully connected future module: {cog_name}")
                except Exception as e:
                    print(f"❌ Failed to load {cog_name}: {e}")
    print("-----------------------------------------------------")

# Dynamically link the setup hook to your working bot
bot.setup_hook = dynamic_setup_hook

@bot.event
async def on_ready():
    print(f"✅ {bot.user.name} is online and connected to Discord!")
    # This fires up the web server in the background as soon as the bot is ready
    bot.loop.create_task(run_web_server())
    print("[System] Web dashboard server has started successfully.")

if __name__ == "__main__":
    if not DISCORD_BOT_TOKEN:
        print("[Critical Error] DISCORD_BOT_TOKEN is missing from your .env file!")
    else:
        # Start the bot using your token
        bot.run(DISCORD_BOT_TOKEN)
