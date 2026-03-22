from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    ContextTypes, ConversationHandler, CallbackQueryHandler,
    MessageHandler, filters,
)
from bot.services.database import add_flight, get_user_flights
from bot.services.aviasales import get_cheapest_prices
from bot.services.gemini import parse_flight_request
from bot.utils.keyboards import cancel_keyboard, main_menu_keyboard, post_track_keyboard
from bot.utils.formatters import format_flight_card
from bot.config import MAX_TRACKED_FLIGHTS

WAITING_INPUT, CONFIRM = range(2)


async def track_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_flights = await get_user_flights(query.from_user.id)
    if len(user_flights) >= MAX_TRACKED_FLIGHTS:
        await query.edit_message_text(
            f"⚠️ En fazla <b>{MAX_TRACKED_FLIGHTS}</b> uçuş takip edebilirsiniz.\n"
            "Yeni uçuş eklemek için önce birini kaldırın.",
            parse_mode="HTML",
            reply_markup=main_menu_keyboard(),
        )
        return ConversationHandler.END

    await query.edit_message_text(
        "✈️ <b>Nereye uçmak istiyorsunuz?</b>\n\n"
        "Doğal dilde yazabilirsiniz, örneğin:\n"
        "• <i>İstanbul'dan Antalya'ya 15 Nisan</i>\n"
        "• <i>Ankara'dan İzmir'e 1 Mayıs, dönüş 10 Mayıs</i>\n"
        "• <i>SAW'dan Londra'ya 20 Haziran gidiş dönüşsüz</i>\n\n"
        "IATA kodu da yazabilirsiniz (IST, AYT, vb.)",
        parse_mode="HTML",
        reply_markup=cancel_keyboard(),
    )
    return WAITING_INPUT


async def user_input_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    await update.message.reply_text("🤖 Anlıyorum, uçuş bilgileri çıkarılıyor...")

    parsed = await parse_flight_request(text)

    if "error" in parsed:
        await update.message.reply_text(
            f"❌ {parsed['error']}\n\nLütfen tekrar deneyin.",
            parse_mode="HTML",
            reply_markup=cancel_keyboard(),
        )
        return WAITING_INPUT

    origin = parsed.get("origin", "").upper()
    destination = parsed.get("destination", "").upper()
    depart_date = parsed.get("depart_date", "")
    return_date = parsed.get("return_date")

    if not origin or not destination or not depart_date:
        await update.message.reply_text(
            "❌ Kalkış, varış veya tarih bilgisi eksik.\n"
            "Lütfen daha detaylı yazın.",
            parse_mode="HTML",
            reply_markup=cancel_keyboard(),
        )
        return WAITING_INPUT

    context.user_data["origin"] = origin
    context.user_data["destination"] = destination
    context.user_data["depart_date"] = depart_date
    context.user_data["return_date"] = return_date if return_date != "null" else None

    ret_str = f"\n📅 Dönüş: <b>{return_date}</b>" if return_date and return_date != "null" else ""

    confirm_kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Onayla", callback_data="confirm_track")],
        [InlineKeyboardButton("🔄 Tekrar Yaz", callback_data="retry_track")],
        [InlineKeyboardButton("🔙 İptal", callback_data="cancel")],
    ])

    await update.message.reply_text(
        f"� <b>Şu uçuşu anladım:</b>\n\n"
        f"🛫 Kalkış: <b>{origin}</b>\n"
        f"🛬 Varış: <b>{destination}</b>\n"
        f"📅 Gidiş: <b>{depart_date}</b>{ret_str}\n\n"
        f"Doğru mu?",
        parse_mode="HTML",
        reply_markup=confirm_kb,
    )
    return CONFIRM


async def confirm_track(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    origin = context.user_data["origin"]
    destination = context.user_data["destination"]
    depart_date = context.user_data["depart_date"]
    return_date = context.user_data.get("return_date")

    user_id = query.from_user.id
    chat_id = query.message.chat_id

    flight_id = await add_flight(user_id, chat_id, origin, destination,
                                 depart_date, return_date)
    if flight_id is None:
        await query.edit_message_text(
            f"⚠️ En fazla <b>{MAX_TRACKED_FLIGHTS}</b> uçuş takip edebilirsiniz.",
            parse_mode="HTML",
            reply_markup=main_menu_keyboard(),
        )
        context.user_data.clear()
        return ConversationHandler.END

    await query.edit_message_text("🔍 Fiyat aranıyor...")

    flight = {
        "id": flight_id,
        "origin": origin,
        "destination": destination,
        "depart_date": depart_date,
        "return_date": return_date,
    }
    price_data = await get_cheapest_prices(origin, destination, depart_date, return_date)
    card = await format_flight_card(flight, price_data)

    await query.message.edit_text(
        f"✅ Uçuş takibe eklendi!\n\n{card}\n\n"
        "💡 <b>Ne yapmak istersiniz?</b>",
        parse_mode="HTML",
        reply_markup=post_track_keyboard(flight_id),
        disable_web_page_preview=True,
    )
    context.user_data.clear()
    return ConversationHandler.END


async def retry_track(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data.clear()

    await query.edit_message_text(
        "✈️ <b>Nereye uçmak istiyorsunuz?</b>\n\n"
        "Doğal dilde yazabilirsiniz, örneğin:\n"
        "• <i>İstanbul'dan Antalya'ya 15 Nisan</i>\n"
        "• <i>Ankara'dan İzmir'e 1 Mayıs, dönüş 10 Mayıs</i>\n\n"
        "Tekrar deneyin 👇",
        parse_mode="HTML",
        reply_markup=cancel_keyboard(),
    )
    return WAITING_INPUT


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data.clear()
    await query.edit_message_text(
        "❌ İşlem iptal edildi.",
        parse_mode="HTML",
        reply_markup=main_menu_keyboard(),
    )
    return ConversationHandler.END


def get_track_conversation() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[CallbackQueryHandler(track_start, pattern="^track$")],
        states={
            WAITING_INPUT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, user_input_received),
            ],
            CONFIRM: [
                CallbackQueryHandler(confirm_track, pattern="^confirm_track$"),
                CallbackQueryHandler(retry_track, pattern="^retry_track$"),
                CallbackQueryHandler(cancel, pattern="^cancel$"),
            ],
        },
        fallbacks=[
            CallbackQueryHandler(cancel, pattern="^cancel$"),
        ],
        per_message=False,
    )
