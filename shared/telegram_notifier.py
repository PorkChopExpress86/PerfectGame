import os
import requests
from dotenv import load_dotenv

# Add project dir to path so imports work from cron
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(SCRIPT_DIR)
load_dotenv(os.path.join(ROOT_DIR, ".env"))

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

def send_telegram(header: str, body: str):
    """
    Send a Telegram message using the bot token and chat ID from .env.
    Matches the pattern used in ~/scripts/daily_summary.sh.
    """
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("WARNING: TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not set in .env")
        return

    # Add team page link to the body
    team_url = os.getenv("PLAYER_TEAM_URL", "")
    team_name = os.getenv("PLAYER_TEAM", "Team Page")
    if team_url:
        body += f"\n\n🔗 <a href=\"{team_url}\">{team_name}</a>"

    message = f"<b>{header}</b>\n\n{body}"
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": "true"
    }

    try:
        response = requests.post(url, data=payload)
        response.raise_for_status()
        print(f"✅ Telegram notification sent to {TELEGRAM_CHAT_ID}")
        return True
    except Exception as e:
        print(f"❌ Failed to send Telegram message: {e}")
        return False
