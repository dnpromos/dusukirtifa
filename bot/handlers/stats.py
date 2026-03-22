from telegram import Update
from telegram.ext import ContextTypes
from bot.services.database import get_user_flights
from bot.services.aviasales import get_cheapest_prices, get_price_stats
from bot.utils.formatters import format_flight_card
from bot.utils.keyboards import back_to_menu_keyboard, main_menu_keyboard


async def stats_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
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

    await query.edit_message_text("🔍 Fiyatlar ve istatistikler alınıyor...")

    cards = []
    for flight in flights:
        month = flight["depart_date"][:7]
        price_data = await get_cheapest_prices(
            flight["origin"], flight["destination"],
            flight["depart_date"], flight.get("return_date"),
        )
        stats = await get_price_stats(
            flight["origin"], flight["destination"], month,
        )
        card = await format_flight_card(flight, price_data, stats)
        cards.append(card)

    text = "\n\n" + ("─" * 28 + "\n\n").join(cards)

    await query.message.edit_text(
        f"📊 <b>Fiyat İstatistikleri</b>\n{text}",
        parse_mode="HTML",
        reply_markup=back_to_menu_keyboard(),
        disable_web_page_preview=True,
    )
