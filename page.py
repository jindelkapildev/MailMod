import os
import time
import math
from quart import Quart, render_template_string, request
from bot_instance import bot  # Pulling bot instance safely
from supabase import create_client, Client

app = Quart(__name__)

# Track when the dashboard script loaded
START_TIME = time.time()

# Initialize Supabase Client inside page.py to fetch mail details for the web view
supabase_url = os.getenv("SUPABASE_URL")
supabase_key = os.getenv("SUPABASE_KEY")
supabase: Client = None

if supabase_url and supabase_key:
    supabase = create_client(supabase_url, supabase_key)

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
                --border-color: rgba(255, 255, 255, 0.08);
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
            h1 {{ font-size: 2rem; margin: 10px 0 5px 0; }}
            .status-badge {{
                display: inline-flex;
                align-items: center;
                background: rgba(46, 204, 113, 0.1);
                color: var(--success-color);
                padding: 6px 16px;
                border-radius: 20px;
                font-size: 0.9rem;
                font-weight: 600;
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
            .stat-value {{ font-size: 1.6rem; font-weight: bold; margin-bottom: 4px; }}
            .stat-label {{ font-size: 0.85rem; color: var(--text-muted); text-transform: uppercase; }}
            
            /* Styles for Single Mail View */
            .mail-header {{
                border-bottom: 1px solid var(--border-color);
                padding-bottom: 20px;
                margin-bottom: 20px;
                text-align: left;
            }}
            .mail-meta {{
                font-size: 0.9rem;
                color: var(--text-muted);
                margin: 5px 0;
            }}
            .mail-meta strong {{
                color: var(--text-color);
            }}
            .mail-body {{
                background: #121420;
                border-radius: 8px;
                padding: 20px;
                font-family: 'Consolas', 'Courier New', monospace;
                font-size: 0.95rem;
                line-height: 1.6;
                white-space: pre-wrap;
                word-break: break-word;
                border: 1px solid var(--border-color);
                color: #e0e6ed;
                text-align: left;
            }}
            .badge {{
                display: inline-block;
                background: var(--accent-color);
                color: #fff;
                padding: 4px 10px;
                border-radius: 4px;
                font-size: 0.8rem;
                font-weight: bold;
                margin-bottom: 15px;
            }}
            footer {{ text-align: center; margin-top: 30px; font-size: 0.8rem; color: var(--text-muted); }}
        </style>
    </head>
    <body>
        <div class="container">
            {content}
            <footer>Powered by Quart Async Engine</footer>
        </div>
    </body>
    </html>
    """

@app.route('/')
async def home():
    # Gather live statistics from your Discord bot safely
    bot_name = bot.user.name if bot.user else "Mail Notification Bot"
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
        <p style="color: var(--text-muted); margin-top: 0; margin-bottom: 20px;">Dedicated Mail Delivery System</p>
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

# Single mail viewer endpoint (for the dynamic buttons)
@app.route('/view')
async def view_mail():
    record_id = request.args.get('id')
    if not record_id:
        return "Missing mail ID parameter.", 400
        
    if not supabase:
        return "Supabase is not configured on the web server.", 500

    try:
        # Fetch the mail record from Supabase
        response = supabase.table("inbox").select("*").eq("id", record_id).execute()
        if not response.data:
            return "Mail record not found.", 404
            
        record = response.data[0]
        subject = record.get("subject") or "(No Subject)"
        sender = record.get("sender") or "Unknown Sender"
        recipient = record.get("recipient") or record.get("to") or "Unknown Recipient"
        body = record.get("body_text") or record.get("raw_body") or "This email has no content."
        date = record.get("created_at", "Unknown Date")[:16].replace("T", " ")

        mail_content = f"""
        <div class="profile-card" style="text-align: left;">
            <span class="badge">SECURE MAIL READER</span>
            <div class="mail-header">
                <h1 style="text-align: left; margin-bottom: 15px;">{subject}</h1>
                <div class="mail-meta"><strong>From:</strong> {sender}</div>
                <div class="mail-meta"><strong>To:</strong> {recipient}</div>
                <div class="mail-meta"><strong>Received:</strong> {date}</div>
            </div>
            <div class="mail-body">{body}</div>
        </div>
        """
        return get_base_html(f"View Mail: {subject}", mail_content)

    except Exception as e:
        return f"Error loading mail content: {str(e)}", 500

async def run_web_server():
    port = int(os.environ.get("PORT", 8080))
    await app.run_task(host="0.0.0.0", port=port)
