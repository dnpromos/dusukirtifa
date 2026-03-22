import asyncio
import logging

import httpx
from telegram.ext import Application
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from bot.config import DAILY_ALERT_HOUR, DAILY_ALERT_MINUTE
from bot.services.database import get_all_tracked_flights, update_last_price
from bot.services.aviasales import batch_fetch_prices, batch_fetch_stats
from bot.utils.formatters import format_flight_card

logger = logging.getLogger(__name__)

TELEGRAM_SEND_DELAY = 0.05


async def send_daily_alerts(app: Application):
    flights = await get_all_tracked_flights()
    if not flights:
        return

    logger.info(f"Starting daily alerts for {len(flights)} tracked flights")

    routes = []
    route_months = []
    for f in flights:
        routes.append((f["origin"], f["destination"],
                        f["depart_date"], f.get("return_date")))
        route_months.append((f["origin"], f["destination"],
                             f["depart_date"][:7]))

    unique_routes = list(set(routes))
    unique_months = list(set(route_months))
    logger.info(f"Deduplicated to {len(unique_routes)} price lookups "
                f"and {len(unique_months)} stat lookups")

    async with httpx.AsyncClient() as client:
        price_cache, stats_cache = await asyncio.gather(
            batch_fetch_prices(unique_routes, client),
            batch_fetch_stats(unique_months, client),
        )

    user_flights: dict[int, list[dict]] = {}
    for f in flights:
        user_flights.setdefault(f["chat_id"], []).append(f)

    sent = 0
    for chat_id, flight_list in user_flights.items():
        cards = []
        for flight in flight_list:
            price_key = (f"{flight['origin']}-{flight['destination']}-"
                         f"{flight['depart_date']}-{flight.get('return_date') or ''}")
            stats_key = (f"{flight['origin']}-{flight['destination']}-"
                         f"{flight['depart_date'][:7]}")

            price_data = price_cache.get(price_key)
            stats = stats_cache.get(stats_key)

            card = await format_flight_card(flight, price_data, stats)
            cards.append(card)

            if price_data and "price" in price_data:
                await update_last_price(flight["id"], price_data["price"])

        text = "\n\n" + ("─" * 28 + "\n\n").join(cards)
        try:
            await app.bot.send_message(
                chat_id=chat_id,
                text=f"🔔 <b>Günlük Fiyat Bildirimi</b>\n{text}",
                parse_mode="HTML",
                disable_web_page_preview=True,
            )
            sent += 1
            await asyncio.sleep(TELEGRAM_SEND_DELAY)
        except Exception as e:
            logger.error(f"Failed to send alert to {chat_id}: {e}")

    logger.info(f"Daily alerts sent to {sent}/{len(user_flights)} users")


def setup_scheduler(app: Application) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone="Europe/Istanbul")
    scheduler.add_job(
        send_daily_alerts,
        trigger="cron",
        hour=DAILY_ALERT_HOUR,
        minute=DAILY_ALERT_MINUTE,
        args=[app],
        id="daily_alerts",
        replace_existing=True,
    )
    return scheduler
