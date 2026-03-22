from telegram import Update
from telegram.ext import ContextTypes

from bot.services.database import get_user_flights
from bot.services.aviasales import get_trend_data
from bot.utils.formatters import format_trend
from bot.utils.keyboards import (
    flight_trend_keyboard, back_to_menu_keyboard, main_menu_keyboard,
)


async def trends_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    flights = await get_user_flights(query.from_user.id)
    if not flights:
        await query.edit_message_text(
            "📭 Takip ettiğiniz uçuş bulunmuyor.",
            parse_mode="HTML",
            reply_markup=main_menu_keyboard(),
        )
        return

    if len(flights) == 1:
        await _show_trend(query, flights[0])
        return

    await query.edit_message_text(
        "📈 <b>Hangi uçuşun fiyat trendini görmek istersiniz?</b>",
        parse_mode="HTML",
        reply_markup=flight_trend_keyboard(flights),
    )


async def trend_detail_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    flight_id = int(query.data.replace("trend_", ""))
    flights = await get_user_flights(query.from_user.id)

    flight = next((f for f in flights if f["id"] == flight_id), None)
    if not flight:
        await query.edit_message_text(
            "⚠️ Uçuş bulunamadı.",
            parse_mode="HTML",
            reply_markup=main_menu_keyboard(),
        )
        return

    await _show_trend(query, flight)


async def _show_trend(query, flight: dict):
    await query.edit_message_text("📈 Fiyat trendleri yükleniyor...")

    month = flight["depart_date"][:7]
    trend = await get_trend_data(flight["origin"], flight["destination"], month)
    text = format_trend(trend, flight["origin"], flight["destination"])

    await query.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=back_to_menu_keyboard(),
        disable_web_page_preview=True,
    )
