import os
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
AVIASALES_API_TOKEN = os.getenv("AVIASALES_API_TOKEN", "")

AVIASALES_BASE_URL = "https://api.travelpayouts.com"

MAX_TRACKED_FLIGHTS = 3

DATABASE_URL = os.getenv("DATABASE_URL", "")

DAILY_ALERT_HOUR = int(os.getenv("DAILY_ALERT_HOUR", "9"))
DAILY_ALERT_MINUTE = int(os.getenv("DAILY_ALERT_MINUTE", "0"))

CURRENCY = "TRY"
PARTNER_MARKER = "531518"
PARTNER_TRS = "510608"

WIRO_API_KEY = os.getenv("WIRO_API_KEY", "")
WIRO_API_SECRET = os.getenv("WIRO_API_SECRET", "")
WIRO_BASE_URL = "https://api.wiro.ai/v1"

_railway_domain = os.getenv("RAILWAY_PUBLIC_DOMAIN", "")
WEBHOOK_BASE_URL = f"https://{_railway_domain}" if _railway_domain else os.getenv("WEBHOOK_BASE_URL", "")
WEBHOOK_PORT = int(os.getenv("PORT", os.getenv("WEBHOOK_PORT", "8080")))
