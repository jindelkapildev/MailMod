import os
import time
import math
import aiohttp
from quart import Quart, render_template_string, request
from bot_instance import bot  
from supabase import create_client, Client

app = Quart(__name__)
START_TIME = time.time()

# Initialize Supabase
supabase_url = os.getenv("SUPABASE_URL")
supabase_key = os.getenv("SUPABASE_KEY")
supabase = create_client(supabase_url, supabase_key) if supabase_url and supabase_key else None

CF_ACCOUNT_ID = os.getenv("CLOUDFLARE_ACCOUNT_ID")
CF_DATABASE_ID = os.getenv("CLOUDFLARE_DATABASE_ID")
CF_API_TOKEN = os.getenv("CLOUDFLARE_API_TOKEN")

async def fetch_from_cloudflare(record_uid):
    """Fallback search targeting the UUID string format (uid field)."""
    if not all([CF_ACCOUNT_ID, CF_DATABASE_ID, CF_API_TOKEN]): return None
    url = f"https://api.cloudflare.com/client/v4/accounts/{CF_ACCOUNT_ID}/d1/database/{CF_DATABASE_ID}/query"
    headers = {"Authorization": f"Bearer {CF_API_TOKEN}", "Content-Type": "application/json"}
    payload = {"sql": "SELECT * FROM inbox WHERE uid = ? LIMIT 1", "params": [record_uid]}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=payload) as response:
                if response.status == 200:
                    res_json = await response.json()
                    if res_json.get("success") and res_json["result"][0]["results"]:
                        return res_json["result"][0]["results"][0]
    except Exception as e: print(f"Cloudflare recovery engine failure: {e}")
    return None

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
                --bg-color: #0f111a; --card-bg: #1e2235; --accent-color: #4e73df;
                --success-color: #2ecc71; --text-color: #f8f9fc; --text-muted: #a0aec0;
                --border-color: rgba(255, 255, 255, 0.08);
            }}
            body {{ font-family: 'Segoe UI', sans-serif; background-color: var(--bg-color); color: var(--text-color); margin:0; padding:0; display:flex; justify-content:center; align-items:center; min-height:100vh; }}
            .container {{ width: 100%; max-width: 800px; padding: 20px; }}
            .profile-card {{ background: var(--card-bg); border-radius: 16px; padding: 30px; border: 1px solid rgba(255,255,255,0.05); margin-bottom: 24px; }}
            .avatar {{ width: 100px; height: 100px; border-radius: 50%; border: 4px solid var(--accent-color); margin-bottom: 15px; }}
            h1 {{ font-size: 2rem; margin: 10px 0 5px 0; }}
            .status-badge {{ display: inline-flex; align-items: center; background: rgba(46, 204, 113, 0.1); color: var(--success-color); padding: 6px 16px; border-radius: 20px; font-size: 0.9rem; }}
            .status-dot {{ width: 8px; height: 8px; background-color: var(--success-color); border-radius: 50%; margin-right: 8px; }}
            .stats-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 16px; }}
            .stat-card {{ background: var(--card-bg); border-radius: 12px; padding: 20px; text-align: center; }}
            .mail-header {{ border-bottom: 1px solid var(--border-color); padding-bottom: 20px; margin-bottom: 20px; }}
            .mail-meta {{ font-size: 0.9rem; color: var(--text-muted); margin: 5px 0; }}
            .mail-body {{ background: #121420; border-radius: 8px; padding: 20px; font-family: monospace; white-space: pre-wrap; }}
            .badge {{ display: inline-block; background: var(--accent-color); color: #fff; padding: 4px 10px; border-radius: 4px; font-size: 0.8rem; margin-bottom: 15px; }}
            footer {{ text-align: center; margin-top: 30px; font-size: 0.8rem; color: var(--text-muted); }}
        </style>
    </head>
    <body>
        <div class="container">{content}<footer>Powered by Quart Async Engine</footer></div>
    </body>
    </html>
    """

@app.route('/')
async def home():
    bot_name = bot.user.name if bot.user else "Mail Notification Bot"
    avatar_url = bot.user.avatar.url if bot.user and bot.user.avatar else "https://cdn.discordapp.com/embed/avatars/0.png"
    guild_count = len(bot.guilds)
    total_users = sum(g.member_count for g in bot.guilds) if bot.guilds else 0
    latency = round(bot.latency * 1000) if bot.latency and not math.isnan(bot.latency) else 0   
    uptime_seconds = int(time.time() - START_TIME)
    uptime_string = f"{uptime_seconds // 3600}h {(uptime_seconds % 3600) // 60}m"

    homepage_content = f"""
    <div class="profile-card">
        <img class="avatar" src="{avatar_url}">
        <h1>{bot_name}</h1>
        <div class="status-badge"><span class="status-dot"></span>ONLINE</div>
    </div>
    <div class="stats-grid">
        <div class="stat-card"><div class="stat-value">{guild_count}</div><div class="stat-label">Servers</div></div>
        <div class="stat-card"><div class="stat-value">{total_users}</div><div class="stat-label">Users</div></div>
        <div class="stat-card"><div class="stat-value">{latency}ms</div><div class="stat-label">Ping</div></div>
        <div class="stat-card"><div class="stat-value">{uptime_string}</div><div class="stat-label">Uptime</div></div>
    </div>
    """
    return get_base_html(f"{bot_name} - Dashboard", homepage_content)

@app.route('/view')
async def view_mail():
    record_uid = request.args.get('id')  # This is the incoming generated UUID
    if not record_uid: return "Missing mail ID parameter.", 400

    record = None
    
    # 1. Look inside Supabase via the uid column
    if supabase:
        try:
            response = supabase.table("inbox").select("*").eq("uid", record_uid).execute()
            if response.data: record = response.data[0]
        except Exception as e: print(f"Supabase checking failure: {e}")

    # 2. Look inside Cloudflare D1 via the uid column
    if not record:
        record = await fetch_from_cloudflare(record_uid)
        
    if not record: return "Mail record not found in Supabase or Cloudflare.", 404
            
    subject = record.get("subject") or "(No Subject)"
    sender = record.get("sender") or "Unknown Sender"
    recipient = record.get("recipient") or record.get("to") or "Unknown Recipient"
    
    html_content = record.get("body_html") or record.get("html_body") or record.get("html")
    plain_text_content = record.get("body_text") or record.get("raw_body") or "This email has no content."

    mail_display = f'<div style="background: white; color: black; border-radius: 8px; padding: 20px; overflow-x: auto;">{html_content}</div>' if html_content else f'<div class="mail-body">{plain_text_content}</div>'

    mail_content = f"""
    <div class="profile-card" style="text-align: left;">
        <span class="badge">SECURE MAIL READER</span>
        <div class="mail-header">
            <h1 style="margin-bottom: 15px; color: #fff;">{subject}</h1>
            <div class="mail-meta"><strong>From:</strong> {sender}</div>
            <div class="mail-meta"><strong>To:</strong> {recipient}</div>
            <div class="mail-meta"><strong>Received:</strong> {record.get("created_at", "Unknown Date")[:16].replace("T", " ")}</div>
        </div>
        {mail_display}
    </div>
    """
    return get_base_html(f"View Mail: {subject}", mail_content)

async def run_web_server():
    port = int(os.environ.get("PORT", 8080))
    await app.run_task(host="0.0.0.0", port=port)
