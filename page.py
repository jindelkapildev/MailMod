import os
import time
import uuid
import math
from quart import Quart, request, render_template_string
from bot_instance import bot  # Pulling bot instance safely
from local_logger import save_to_history  # Import your existing db logic

app = Quart(__name__)

# Track when the dashboard script loaded
START_TIME = time.time()

# A dictionary to temporarily hold valid tokens and track channel info
ACTIVE_TOKENS = {}

# Reusable template wrapper to keep the theme identical across all pages
def get_base_html(title, content):
    return f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>{title}</title>
        <style>
            :root {{
                --bg-color: #0f111a;
                --card-bg: #1e2235;
                --accent-color: #4e73df;
                --success-color: #2ecc71;
                --text-color: #f8f9fc;
                --text-muted: #a0aec0;
                --danger-color: #e74c3c;
            }}
            
            body {{
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                background-color: var(--bg-color);
                color: var(--text-color);
                margin: 0;
                padding: 0;
                display: flex;
                justify-content: center;
                align-items: center;
                min-height: 100vh;
            }}

            .container {{
                width: 100%;
                max-width: 800px;
                padding: 20px;
                box-sizing: border-box;
            }}

            .profile-card {{
                background: var(--card-bg);
                border-radius: 16px;
                padding: 30px;
                text-align: center;
                box-shadow: 0 10px 30px rgba(0,0,0,0.5);
                border: 1px solid rgba(255,255,255,0.05);
                margin-bottom: 24px;
            }}

            .avatar {{
                width: 100px;
                height: 100px;
                border-radius: 50%;
                border: 4px solid var(--accent-color);
                box-shadow: 0 0 20px rgba(78, 115, 223, 0.5);
                margin-bottom: 15px;
            }}

            h1, h2 {{
                margin: 10px 0 5px 0;
                letter-spacing: 0.5px;
            }}
            
            h1 {{ font-size: 2rem; }}
            h2 {{ font-size: 1.5rem; color: #4fffc0; text-align: left; margin-bottom: 15px; }}

            .status-badge {{
                display: inline-flex;
                align-items: center;
                background: rgba(46, 204, 113, 0.1);
                color: var(--success-color);
                padding: 6px 16px;
                border-radius: 20px;
                font-size: 0.9rem;
                font-weight: 600;
                letter-spacing: 0.5px;
                border: 1px solid rgba(46, 204, 113, 0.2);
            }}

            .status-dot {{
                width: 8px;
                height: 8px;
                background-color: var(--success-color);
                border-radius: 50%;
                margin-right: 8px;
                box-shadow: 0 0 10px var(--success-color);
            }}

            .stats-grid {{
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
                gap: 16px;
            }}

            .stat-card {{
                background: var(--card-bg);
                border-radius: 12px;
                padding: 20px;
                text-align: center;
                border: 1px solid rgba(255,255,255,0.02);
                box-shadow: 0 4px 15px rgba(0,0,0,0.2);
                transition: transform 0.2s ease;
            }}

            .stat-card:hover {{
                transform: translateY(-3px);
                border-color: rgba(78, 115, 223, 0.3);
            }}

            .stat-value {{
                font-size: 1.6rem;
                font-weight: bold;
                color: var(--text-color);
                margin-bottom: 4px;
            }}

            .stat-label {{
                font-size: 0.85rem;
                color: var(--text-muted);
                text-transform: uppercase;
                letter-spacing: 1px;
            }}

            /* Push Portal Specific Elements */
            textarea {{
                width: 100%;
                height: 350px;
                background-color: #121420;
                color: #00ff66;
                border: 1px solid rgba(255,255,255,0.1);
                border-radius: 8px;
                padding: 15px;
                font-family: monospace;
                font-size: 14px;
                box-sizing: border-box;
                resize: vertical;
                margin-bottom: 15px;
            }}
            
            textarea:focus {{
                outline: none;
                border-color: var(--accent-color);
                box-shadow: 0 0 10px rgba(78, 115, 223, 0.3);
            }}

            button {{
                background-color: var(--accent-color);
                color: white;
                border: none;
                padding: 14px 24px;
                font-size: 16px;
                font-weight: bold;
                border-radius: 8px;
                cursor: pointer;
                width: 100%;
                transition: background 0.2s, transform 0.1s;
                box-shadow: 0 4px 15px rgba(78, 115, 223, 0.3);
            }}
            
            button:hover {{ background-color: #355bc7; transform: translateY(-1px); }}
            button:active {{ transform: translateY(1px); }}

            footer {{
                text-align: center;
                margin-top: 30px;
                font-size: 0.8rem;
                color: var(--text-muted);
            }}
        </style>
    </head>
    <body>
        <div class="container">
            {content}
            <footer>
                Powered by Quart & Render Async Architecture
            </footer>
        </div>
    </body>
    </html>
    """

@app.route('/')
async def home():
    # Gather live statistics from your Discord bot safely
    bot_name = bot.user.name if bot.user else "Clan War Tracker"
    avatar_url = bot.user.avatar.url if bot.user and bot.user.avatar else "https://cdn.discordapp.com/embed/avatars/0.png"
    guild_count = len(bot.guilds)
    total_users = sum(g.member_count for g in bot.guilds) if bot.guilds else 0
    
    # SAFE LATENCY CHECK (Prevents float NaN crashes)
    if bot.latency and not math.isnan(bot.latency):
        latency = round(bot.latency * 1000)
    else:
        latency = 0   
        
    # Simple uptime calculation
    uptime_seconds = int(time.time() - START_TIME)
    uptime_hours = uptime_seconds // 3600
    uptime_mins = (uptime_seconds % 3600) // 60
    uptime_string = f"{uptime_hours}h {uptime_mins}m"

    homepage_content = f"""
    <div class="profile-card">
        <img class="avatar" src="{avatar_url}" alt="Bot Avatar">
        <h1>{bot_name}</h1>
        <p style="color: var(--text-muted); margin-top: 0; margin-bottom: 20px;">Clash of Clans Tracker</p>
        <div class="status-badge">
            <span class="status-dot"></span>
            ONLINE & OPERATIONAL
        </div>
    </div>

    <div class="stats-grid">
        <div class="stat-card">
            <div class="stat-value">{guild_count}</div>
            <div class="stat-label">Servers</div>
        </div>
        <div class="stat-card">
            <div class="stat-value">{total_users}</div>
            <div class="stat-label">Users Tracking</div>
        </div>
        <div class="stat-card">
            <div class="stat-value">{latency}ms</div>
            <div class="stat-label">Ping Latency</div>
        </div>
        <div class="stat-card">
            <div class="stat-value">{uptime_string}</div>
            <div class="stat-label">Uptime</div>
        </div>
    </div>
    """
    return get_base_html(f"{bot_name} - Dashboard", homepage_content)

# GET Route: Displays the Unlimited Submission Text Portal
@app.route('/push/<token>', methods=['GET'])
async def view_push_page(token):
    if token not in ACTIVE_TOKENS:
        error_content = """
        <div class="profile-card" style="border-color: var(--danger-color);">
            <h1 style="color: var(--danger-color); font-size: 3.5rem; margin-bottom: 10px;">❌</h1>
            <h1>Link Expired or Invalid</h1>
            <p style="color: var(--text-muted); margin-top: 15px;">Please generate a fresh temporary transmission link using <code>?push</code> in Discord.</p>
        </div>
        """
        return get_base_html("Link Expired - ClashHunt", error_content), 403

    portal_content = """
    <div class="profile-card" style="text-align: left;">
        <h2>🌐 ClashHunt Data Submission Portal</h2>
        <p style="color: var(--text-muted); font-size: 0.95rem; margin-bottom: 25px; line-height: 1.5;">
            Paste your raw JSON data string inside the entry window below. Because this submission runs over direct HTTP streams, there are absolutely <b>no size or character limitations</b>.
        </p>
        <form method="POST">
            <textarea name="json_data" placeholder="Paste your raw JSON content here..." required></textarea>
            <button type="submit">🚀 Sync data to MongoDB Database</button>
        </form>
        <p style="color: var(--text-muted); font-size: 0.8rem; text-align: center; margin-top: 15px; margin-bottom: 0;">
            ⚠️ This secure link will destroy itself automatically immediately upon submission or after 10 minutes.
        </p>
    </div>
    """
    return get_base_html("Submit Data - ClashHunt", portal_content)

# POST Route: Processes the massive JSON data string
@app.route('/push/<token>', methods=['POST'])
async def handle_push_submit(token):
    if token not in ACTIVE_TOKENS:
        error_content = """
        <div class="profile-card" style="border-color: var(--danger-color);">
            <h1>❌ Access Terminated</h1>
        </div>
        """
        return get_base_html("Error - ClashHunt", error_content), 403
    
    form = await request.form
    raw_data = form.get("json_data", "").strip()
    
    # Extract channel reference info before revoking the token access
    ctx_info = ACTIVE_TOKENS.pop(token) 
    
    if not raw_data:
        error_content = """
        <div class="profile-card" style="border-color: var(--danger-color);">
            <h1>❌ Submission Rejected</h1>
            <p style="color: var(--text-muted);">Data payload cannot be empty.</p>
        </div>
        """
        return get_base_html("Failed - ClashHunt", error_content), 400

    try:
        # Fire off your local_logger parsing loop
        save_to_history(raw_data)
        
        # Ping the originating discord channel asynchronously to announce success
        channel = bot.get_channel(ctx_info["channel_id"])
        if channel:
            bot.loop.create_task(
                channel.send(f"✅ **Web Sync Complete:** Giant raw data string submitted by <@{ctx_info['author_id']}> processed successfully and synced to MongoDB!")
            )

        success_content = """
        <div class="profile-card" style="border-color: var(--success-color);">
            <h1 style="color: var(--success-color); font-size: 3.5rem; margin-bottom: 10px;">✅</h1>
            <h1>Data Synchronized!</h1>
            <p style="color: var(--text-muted); margin-top: 15px;">Your local configurations and MongoDB cluster were successfully updated. You can now close this browser tab.</p>
        </div>
        """
        return get_base_html("Success - ClashHunt", success_content)

    except Exception as e:
        failure_content = f"""
        <div class="profile-card" style="border-color: var(--danger-color);">
            <h1 style="color: var(--danger-color);">❌ Database Synced Error</h1>
            <p style="color: var(--text-muted); font-family: monospace; font-size: 0.9rem; background: #121420; padding: 15px; border-radius: 6px; text-align: left; overflow-x: auto;">{str(e)}</p>
        </div>
        """
        return get_base_html("Execution Failed - ClashHunt", failure_content), 500

# Server execution loop initialized dynamically inside main.py
async def run_web_server():
    port = int(os.environ.get("PORT", 8080))
    await app.run_task(host="0.0.0.0", port=port)
