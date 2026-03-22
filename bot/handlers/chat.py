from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    ContextTypes, ConversationHandler, CallbackQueryHandler,
    MessageHandler, filters,
)
from bot.services.gemini import chat as gemini_chat
from bot.services.aviasales import (
    get_cheapest_prices, get_popular_routes,
    get_direct_flights, get_trend_data,
)
from bot.services.database import add_flight, get_user_flights
from bot.utils.formatters import (
    format_flight_card, format_popular_routes,
    format_direct_flights, format_trend,
)
from bot.utils.keyboards import main_menu_keyboard, post_track_keyboard
from bot.config import MAX_TRACKED_FLIGHTS

CHATTING = 0


def _chat_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 Ana Menü", callback_data="end_chat")],
    ])


def _confirm_track_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Takibe Al", callback_data="chat_track_yes")],
        [InlineKeyboardButton("💬 Sohbete Devam", callback_data="chat_track_no")],
        [InlineKeyboardButton("🔙 Ana Menü", callback_data="end_chat")],
    ])


async def chat_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    context.user_data["chat_history"] = []

    await query.edit_message_text(
        "🤖 <b>AI Asistan</b>\n\n"
        "Merhaba! Ben Düşük İrtifa, uçuş asistanınım. ✈️\n\n"
        "Benimle doğal bir şekilde konuşabilirsin:\n"
        "• <i>En ucuz Antalya uçuşu ne zaman?</i>\n"
        "• <i>İstanbul'dan nereye ucuza gidebilirim?</i>\n"
        "• <i>Londra'ya direkt uçuş var mı?</i>\n"
        "• <i>Mayıs'ta tatile çıkmak istiyorum, önerir misin?</i>\n\n"
        "Yazın, konuşalım! 💬",
        parse_mode="HTML",
        reply_markup=_chat_keyboard(),
    )
    return CHATTING


async def chat_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    history = context.user_data.get("chat_history", [])

    await update.message.reply_text("🤖 Düşünüyorum...")

    result = await gemini_chat(text, history)

    history.append({"role": "user", "text": text})
    history.append({"role": "assistant", "text": result.get("message", "")})
    context.user_data["chat_history"] = history

    action = result.get("action", "chat")
    message = result.get("message", "")

    if action == "search_flight":
        await _handle_search(update, context, result, message)
    elif action == "show_popular":
        await _handle_popular(update, result, message)
    elif action == "show_direct":
        await _handle_direct(update, result, message)
    elif action == "show_trends":
        await _handle_trends(update, result, message)
    else:
        await update.message.reply_text(
            message,
            parse_mode="HTML",
            reply_markup=_chat_keyboard(),
        )

    return CHATTING


async def _handle_search(update: Update, context: ContextTypes.DEFAULT_TYPE,
                         result: dict, message: str):
    origin = result.get("origin", "").upper()
    destination = result.get("destination", "").upper()
    depart_date = result.get("depart_date", "")
    return_date = result.get("return_date")
    if return_date == "null":
        return_date = None

    if not origin or not destination or not depart_date:
        await update.message.reply_text(
            message,
            parse_mode="HTML",
            reply_markup=_chat_keyboard(),
        )
        return

    context.user_data["pending_flight"] = {
        "origin": origin,
        "destination": destination,
        "depart_date": depart_date,
        "return_date": return_date,
    }

    price_data = await get_cheapest_prices(origin, destination, depart_date, return_date)

    flight_info = {
        "origin": origin,
        "destination": destination,
        "depart_date": depart_date,
        "return_date": return_date,
    }
    card = await format_flight_card(flight_info, price_data)

    await update.message.reply_text(
        f"{message}\n\n{card}\n\n"
        "📌 <b>Bu uçuşu takibe almak ister misin?</b>",
        parse_mode="HTML",
        reply_markup=_confirm_track_keyboard(),
        disable_web_page_preview=True,
    )


async def _handle_popular(update: Update, result: dict, message: str):
    origin = result.get("origin", "").upper()
    if not origin:
        await update.message.reply_text(
            message, parse_mode="HTML", reply_markup=_chat_keyboard(),
        )
        return

    routes = await get_popular_routes(origin)
    text = await format_popular_routes(routes, origin)

    await update.message.reply_text(
        f"{message}\n\n{text}",
        parse_mode="HTML",
        reply_markup=_chat_keyboard(),
        disable_web_page_preview=True,
    )


async def _handle_direct(update: Update, result: dict, message: str):
    origin = result.get("origin", "").upper()
    destination = result.get("destination", "").upper()
    month = result.get("month", "")

    if not origin or not destination or not month:
        await update.message.reply_text(
            message, parse_mode="HTML", reply_markup=_chat_keyboard(),
        )
        return

    direct = await get_direct_flights(origin, destination, month)
    text = await format_direct_flights(direct, origin, destination)

    await update.message.reply_text(
        f"{message}\n\n{text}",
        parse_mode="HTML",
        reply_markup=_chat_keyboard(),
        disable_web_page_preview=True,
    )


async def _handle_trends(update: Update, result: dict, message: str):
    origin = result.get("origin", "").upper()
    destination = result.get("destination", "").upper()
    month = result.get("month", "")

    if not origin or not destination or not month:
        await update.message.reply_text(
            message, parse_mode="HTML", reply_markup=_chat_keyboard(),
        )
        return

    trend = await get_trend_data(origin, destination, month)
    text = format_trend(trend, origin, destination)

    await update.message.reply_text(
        f"{message}\n\n{text}",
        parse_mode="HTML",
        reply_markup=_chat_keyboard(),
        disable_web_page_preview=True,
    )


async def chat_track_yes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    pending = context.user_data.get("pending_flight")
    if not pending:
        await query.edit_message_text(
            "⚠️ Takip edilecek uçuş bulunamadı.",
            parse_mode="HTML",
            reply_markup=_chat_keyboard(),
        )
        return CHATTING

    user_flights = await get_user_flights(query.from_user.id)
    if len(user_flights) >= MAX_TRACKED_FLIGHTS:
        await query.edit_message_text(
            f"⚠️ En fazla <b>{MAX_TRACKED_FLIGHTS}</b> uçuş takip edebilirsiniz.\n"
            "Yeni eklemek için birini kaldırın.\n\n"
            "Sohbete devam edebilirsin 💬",
            parse_mode="HTML",
            reply_markup=_chat_keyboard(),
        )
        return CHATTING

    flight_id = await add_flight(
        query.from_user.id,
        query.message.chat_id,
        pending["origin"],
        pending["destination"],
        pending["depart_date"],
        pending["return_date"],
    )
    context.user_data.pop("pending_flight", None)

    if flight_id is None:
        await query.edit_message_text(
            "⚠️ Uçuş eklenemedi.",
            parse_mode="HTML",
            reply_markup=_chat_keyboard(),
        )
        return CHATTING

    price_data = await get_cheapest_prices(
        pending["origin"], pending["destination"],
        pending["depart_date"], pending["return_date"],
    )
    flight = {**pending, "id": flight_id}
    card = await format_flight_card(flight, price_data)

    await query.message.edit_text(
        f"✅ Uçuş takibe alındı!\n\n{card}\n\n"
        "💬 Sohbete devam edebilirsin.",
        parse_mode="HTML",
        reply_markup=_chat_keyboard(),
        disable_web_page_preview=True,
    )
    return CHATTING


async def chat_track_no(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data.pop("pending_flight", None)

    await query.edit_message_text(
        "👍 Tamam, takibe almadım. Sohbete devam edelim!\n\n"
        "Başka bir şey sormak ister misin? 💬",
        parse_mode="HTML",
        reply_markup=_chat_keyboard(),
    )
    return CHATTING


async def end_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data.pop("chat_history", None)
    context.user_data.pop("pending_flight", None)

    await query.edit_message_text(
        "👋 Görüşmek üzere! Ana menüye dönüyorum.",
        parse_mode="HTML",
        reply_markup=main_menu_keyboard(),
    )
    return ConversationHandler.END


def get_chat_conversation() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[CallbackQueryHandler(chat_start, pattern="^ai_chat$")],
        states={
            CHATTING: [
                CallbackQueryHandler(chat_track_yes, pattern="^chat_track_yes$"),
                CallbackQueryHandler(chat_track_no, pattern="^chat_track_no$"),
                CallbackQueryHandler(end_chat, pattern="^end_chat$"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, chat_message),
            ],
        },
        fallbacks=[
            CallbackQueryHandler(end_chat, pattern="^end_chat$"),
        ],
        per_message=False,
    )
