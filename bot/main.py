import logging

from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters

from bot.config import TELEGRAM_BOT_TOKEN
from bot.services.database import init_db
from bot.services.scheduler import setup_scheduler
from bot.services.airlines import load_airlines
from bot.services.webhook import start_webhook_server
from bot.handlers.start import start_command
from bot.handlers.fallback import handle_message, track_yes_callback, track_no_callback

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)


async def post_init(app: Application):
    await init_db()
    await load_airlines()
    await start_webhook_server()
    scheduler = setup_scheduler(app)
    scheduler.start()
    logger.info("Scheduler started — daily alerts at configured time (Europe/Istanbul)")


def main():
    if not TELEGRAM_BOT_TOKEN:
        raise ValueError("TELEGRAM_BOT_TOKEN is not set in .env")

    app = Application.builder().token(TELEGRAM_BOT_TOKEN).post_init(post_init).build()

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CallbackQueryHandler(track_yes_callback, pattern="^ai_track_yes$"))
    app.add_handler(CallbackQueryHandler(track_no_callback, pattern="^ai_track_no$"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("TeleFlight bot starting...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
