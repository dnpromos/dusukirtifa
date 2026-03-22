import asyncio
import logging

import httpx
from telegram.ext import Application
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from bot.services.database import (
    get_flights_due_for_check, update_flight_price, expire_past_flights,
)
from bot.services.aviasales import batch_fetch_prices
from bot.utils.formatters import format_smart_alert

logger = logging.getLogger(__name__)

TELEGRAM_SEND_DELAY = 0.05
PRICE_CHANGE_PCT = 0.10


async def check_prices(app: Application):
    expired = await expire_past_flights()
    if expired:
        logger.info(f"Auto-expired {expired} past flights")

    flights = await get_flights_due_for_check()
    if not flights:
        logger.info("No flights due for price check")
        return

    logger.info(f"Checking prices for {len(flights)} flights")

    routes = list(set(
        (f["origin"], f["destination"], f["depart_date"], f.get("return_date"))
        for f in flights
    ))

    async with httpx.AsyncClient() as client:
        price_cache = await batch_fetch_prices(routes, client)

    alerts_by_chat: dict[int, list[str]] = {}

    for flight in flights:
        price_key = (
            f"{flight['origin']}-{flight['destination']}-"
            f"{flight['depart_date']}-{flight.get('return_date') or ''}"
        )
        price_data = price_cache.get(price_key)
        if not price_data or "price" not in price_data:
            continue

        new_price = price_data["price"]
        old_price = flight.get("last_price")

        await update_flight_price(flight["id"], new_price)

        if old_price is None:
            continue

        diff = new_price - old_price
        if abs(diff) / old_price < PRICE_CHANGE_PCT:
            continue

        days_until = flight.get("days_until", 999)
        card = await format_smart_alert(flight, price_data, diff, days_until)
        alerts_by_chat.setdefault(flight["chat_id"], []).append(card)

    sent = 0
    for chat_id, cards in alerts_by_chat.items():
        text = "\n\n" + ("─" * 28 + "\n\n").join(cards)
        try:
            await app.bot.send_message(
                chat_id=chat_id,
                text=f"🔔 <b>Fiyat Değişikliği</b>\n{text}",
                parse_mode="HTML",
                disable_web_page_preview=True,
            )
            sent += 1
            await asyncio.sleep(TELEGRAM_SEND_DELAY)
        except Exception as e:
            logger.error(f"Failed to send alert to {chat_id}: {e}")

    logger.info(f"Sent price alerts to {sent} users")


async def send_weekly_digest(app: Application):
    from bot.services.database import get_all_tracked_flights

    flights = await get_all_tracked_flights()
    if not flights:
        return

    user_flights: dict[int, list[dict]] = {}
    for f in flights:
        user_flights.setdefault(f["chat_id"], []).append(f)

    sent = 0
    for chat_id, flight_list in user_flights.items():
        lines = ["📊 <b>Haftalık Takip Özeti</b>\n"]
        for f in flight_list:
            origin = f["origin"]
            dest = f["destination"]
            depart = f["depart_date"]
            price = f.get("last_price")
            lowest = f.get("lowest_price")

            price_str = f"{price:,.0f}₺" if price else "—"
            lowest_str = f"{lowest:,.0f}₺" if lowest else "—"

            lines.append(
                f"✈️ <b>{origin} → {dest}</b> ({depart})\n"
                f"   Güncel: {price_str} · En düşük: {lowest_str}"
            )

        try:
            await app.bot.send_message(
                chat_id=chat_id,
                text="\n\n".join(lines),
                parse_mode="HTML",
                disable_web_page_preview=True,
            )
            sent += 1
            await asyncio.sleep(TELEGRAM_SEND_DELAY)
        except Exception as e:
            logger.error(f"Failed to send digest to {chat_id}: {e}")

    logger.info(f"Weekly digest sent to {sent}/{len(user_flights)} users")


def setup_scheduler(app: Application) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone="Europe/Istanbul")

    scheduler.add_job(
        check_prices,
        trigger="cron",
        hour="9,15,21",
        args=[app],
        id="price_check",
        replace_existing=True,
    )

    scheduler.add_job(
        send_weekly_digest,
        trigger="cron",
        day_of_week="mon",
        hour=10,
        args=[app],
        id="weekly_digest",
        replace_existing=True,
    )

    return scheduler
