import os
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
AVIASALES_API_TOKEN = os.getenv("AVIASALES_API_TOKEN", "")

AVIASALES_BASE_URL = "https://api.travelpayouts.com"

MAX_TRACKED_FLIGHTS = 3

DB_PATH = os.getenv("DB_PATH", "tele_flight.db")

DAILY_ALERT_HOUR = int(os.getenv("DAILY_ALERT_HOUR", "9"))
DAILY_ALERT_MINUTE = int(os.getenv("DAILY_ALERT_MINUTE", "0"))

CURRENCY = "TRY"
PARTNER_MARKER = "531518"
PARTNER_TRS = "510608"

WIRO_API_KEY = os.getenv("WIRO_API_KEY", "")
WIRO_API_SECRET = os.getenv("WIRO_API_SECRET", "")
WIRO_BASE_URL = "https://api.wiro.ai/v1"
