from telegram import Update
from telegram.ext import ContextTypes
from bot.services.database import get_user_flights, remove_flight
from bot.utils.keyboards import flight_remove_keyboard, main_menu_keyboard


async def remove_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
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

    await query.edit_message_text(
        "❌ <b>Kaldırmak istediğiniz uçuşu seçin:</b>",
        parse_mode="HTML",
        reply_markup=flight_remove_keyboard(flights),
    )


async def remove_flight_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    flight_id = int(query.data.replace("rm_", ""))
    removed = await remove_flight(query.from_user.id, flight_id)

    if removed:
        text = "✅ Uçuş takipten kaldırıldı."
    else:
        text = "⚠️ Uçuş bulunamadı veya zaten kaldırılmış."

    await query.edit_message_text(
        text,
        parse_mode="HTML",
        reply_markup=main_menu_keyboard(),
    )
