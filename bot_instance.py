# In your bot initialization file (e.g., bot_instance.py)
import os
import discord
from discord.ext import commands

# 1. Fetch proxy URL from environment variables
PROXY_URL = os.getenv("PROXY_URL") # e.g., http://username:password@proxy_ip:port

# 2. Define your list of multi-prefixes
prefixes = ["!", "?", "$", ";", "%"]

# 3. Setup your Gateway Intents properly
intents = discord.Intents.default()
intents.members = True           # Required to track roles/fetch members
intents.message_content = True   # Required for prefix commands to read messages

# 4. Initialize the Bot instance
bot = commands.Bot(
    command_prefix=prefixes,     # Now accepts any of the prefixes in the list
    proxy=PROXY_URL,             # Routes Discord API traffic through a clean IP
    intents=intents              # Passes the fully configured intents object
)
