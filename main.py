import os
import asyncio
from dotenv import load_dotenv
import discord

# Directly import the working bot instance from your unchanged war_tracker file
from bot_instance import bot
# Import the web server task from your new page.py file
from page import run_web_server

# Set intents before anything else logs in
bot.intents.members = True

load_dotenv()
DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")

async def dynamic_setup_hook():
    """Runs once before the bot connects. Loads cogs and starts the web server safely."""
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
    
    # START THE WEB SERVER HERE
    print("[System] Launching web dashboard server...")
    bot.loop.create_task(run_web_server())

# Dynamically link the setup hook to your working bot
bot.setup_hook = dynamic_setup_hook

@bot.event
async def on_ready():
    print(f"✅ {bot.user.name} is online and connected to Discord!")
    
    # Let's set the initial status to IDLE right when it signs in.
    # It tells Discord: "I am connected, but I am resting/waiting."
    await bot.change_presence(
        status=discord.Status.idle, 
        activity=discord.Game(name="Watching for updates... 👀")
    )
    print("[System] Bot status set to: Idle")

if __name__ == "__main__":
    if not DISCORD_BOT_TOKEN:
        print("[Critical Error] DISCORD_BOT_TOKEN is missing from your .env file!")
    else:
        bot.run(DISCORD_BOT_TOKEN)
