from telegram import Update
from telegram.ext import ContextTypes
from bot.services.database import get_user_flights
from bot.utils.formatters import format_flight_list
from bot.utils.keyboards import back_to_menu_keyboard


async def list_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    flights = await get_user_flights(query.from_user.id)
    text = format_flight_list(flights)

    await query.edit_message_text(
        text,
        parse_mode="HTML",
        reply_markup=back_to_menu_keyboard(),
    )
