from telegram import Update
from telegram.ext import ContextTypes

from bot.services.database import get_user_flights
from bot.services.aviasales import get_direct_flights
from bot.utils.formatters import format_direct_flights
from bot.utils.keyboards import (
    back_to_menu_keyboard, main_menu_keyboard,
)


async def direct_list_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    flights = await get_user_flights(query.from_user.id)
    if not flights:
        await query.edit_message_text(
            "📭 Takip ettiğiniz uçuş bulunmuyor.\n"
            "Önce bir uçuş takip edin.",
            parse_mode="HTML",
            reply_markup=main_menu_keyboard(),
        )
        return

    if len(flights) == 1:
        await _show_direct(query, flights[0])
        return

    from bot.utils.keyboards import flight_direct_keyboard
    await query.edit_message_text(
        "✈️ <b>Hangi uçuş için aktarmasız seferleri görmek istersiniz?</b>",
        parse_mode="HTML",
        reply_markup=flight_direct_keyboard(flights),
    )


async def direct_detail_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    flight_id = int(query.data.replace("direct_", ""))
    flights = await get_user_flights(query.from_user.id)

    flight = next((f for f in flights if f["id"] == flight_id), None)
    if not flight:
        await query.edit_message_text(
            "⚠️ Uçuş bulunamadı.",
            parse_mode="HTML",
            reply_markup=main_menu_keyboard(),
        )
        return

    await _show_direct(query, flight)


async def _show_direct(query, flight: dict):
    await query.edit_message_text("✈️ Aktarmasız uçuşlar aranıyor...")

    month = flight["depart_date"][:7]
    direct = await get_direct_flights(
        flight["origin"], flight["destination"], month,
    )
    text = await format_direct_flights(direct, flight["origin"], flight["destination"])

    await query.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=back_to_menu_keyboard(),
        disable_web_page_preview=True,
    )
