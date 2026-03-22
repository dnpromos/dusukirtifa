from telegram import Update
from telegram.ext import (
    ContextTypes, ConversationHandler, CallbackQueryHandler,
    MessageHandler, filters,
)
from bot.services.aviasales import get_popular_routes
from bot.services.gemini import parse_flight_request
from bot.utils.formatters import format_popular_routes
from bot.utils.keyboards import cancel_keyboard, back_to_menu_keyboard

WAITING_CITY = 0


async def popular_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    await query.edit_message_text(
        "🌍 <b>Hangi şehirden uçmak istiyorsunuz?</b>\n\n"
        "Şehir adı veya havalimanı kodu yazın:\n"
        "• <i>İstanbul</i>\n"
        "• <i>Ankara</i>\n"
        "• <i>IST</i>",
        parse_mode="HTML",
        reply_markup=cancel_keyboard(),
    )
    return WAITING_CITY


async def city_received(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip().upper()

    if len(text) == 3 and text.isalpha():
        origin = text
    else:
        await update.message.reply_text("🤖 Şehir algılanıyor...")
        parsed = await parse_flight_request(
            f"{text} şehrinden herhangi bir yere yarın"
        )
        origin = parsed.get("origin", "").upper()
        if not origin:
            await update.message.reply_text(
                "❌ Şehir anlaşılamadı. IATA kodu veya şehir adı girin.",
                parse_mode="HTML",
                reply_markup=cancel_keyboard(),
            )
            return WAITING_CITY

    await update.message.reply_text("🔍 Popüler rotalar aranıyor...")

    routes = await get_popular_routes(origin)
    text = await format_popular_routes(routes, origin)

    await update.message.reply_text(
        text,
        parse_mode="HTML",
        reply_markup=back_to_menu_keyboard(),
        disable_web_page_preview=True,
    )
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    from bot.utils.keyboards import main_menu_keyboard
    await query.edit_message_text(
        "❌ İşlem iptal edildi.",
        parse_mode="HTML",
        reply_markup=main_menu_keyboard(),
    )
    return ConversationHandler.END


def get_popular_conversation() -> ConversationHandler:
    return ConversationHandler(
        entry_points=[CallbackQueryHandler(popular_start, pattern="^popular$")],
        states={
            WAITING_CITY: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, city_received),
            ],
        },
        fallbacks=[
            CallbackQueryHandler(cancel, pattern="^cancel$"),
        ],
        per_message=False,
    )
