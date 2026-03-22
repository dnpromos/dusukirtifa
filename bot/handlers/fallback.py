import json
import logging
import re

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, constants
from telegram.ext import ContextTypes

from bot.services.gemini import chat as gemini_chat
from bot.services.aviasales import (
    get_cheapest_prices, get_popular_routes,
    get_direct_flights, get_trend_data,
    get_latest_prices, get_month_matrix,
)
from bot.services.database import add_flight, get_user_flights, remove_flight
from bot.utils.formatters import (
    format_flight_card, format_flight_list, format_popular_routes,
    format_direct_flights, format_trend, format_latest_prices,
    format_calendar,
)
from bot.config import MAX_TRACKED_FLIGHTS

logger = logging.getLogger(__name__)


def _safe_upper(val) -> str:
    return (val or "").strip().upper()


def _md_to_html(text: str) -> str:
    text = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', text)
    text = re.sub(r'\*(.+?)\*', r'<i>\1</i>', text)
    text = re.sub(r'`(.+?)`', r'<code>\1</code>', text)
    text = text.replace('### ', '').replace('## ', '').replace('# ', '')
    return text


def _track_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Takibe Al", callback_data="ai_track_yes")],
        [InlineKeyboardButton("❌ Hayır", callback_data="ai_track_no")],
    ])


SEARCH_STATUS = {
    "search_flight": "🔍 Uçuş fiyatlarına bakıyorum...",
    "show_popular": "🌍 Popüler rotaları araştırıyorum...",
    "show_direct": "✈️ Aktarmasız uçuşlara bakıyorum...",
    "show_trends": "📈 Fiyat trendlerini inceliyorum...",
    "show_latest": "🔥 Son bulunan biletleri getiriyorum...",
    "show_calendar": "📅 Fiyat takvimini hazırlıyorum...",
}


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if not text:
        return

    history = context.user_data.get("chat_history", [])

    await update.effective_chat.send_action(constants.ChatAction.TYPING)

    try:
        result = await gemini_chat(text, history)
    except Exception as e:
        logger.error(f"AI chat error: {e}")
        await update.message.reply_text(
            "⚠️ Bir hata oluştu, tekrar dener misin?",
            parse_mode="HTML",
        )
        return

    ai_message = _md_to_html(result.get("message", ""))
    history.append({"role": "user", "text": text})

    assistant_entry = {"role": "assistant", "text": ai_message}
    action = result.get("action", "chat")
    if action != "chat":
        params = {k: v for k, v in result.items() if k != "message"}
        assistant_entry["text"] = f"{ai_message}\n[Aksiyon: {json.dumps(params, ensure_ascii=False)}]"
    history.append(assistant_entry)
    context.user_data["chat_history"] = history

    status_text = SEARCH_STATUS.get(action)
    status_msg = None
    if status_text:
        status_msg = await update.message.reply_text(
            f"{ai_message}\n\n{status_text}",
            parse_mode="HTML",
        )

    try:
        if action == "search_flight":
            await _do_search(update, context, result, ai_message, status_msg)
        elif action == "show_popular":
            await _do_popular(update, result, ai_message, status_msg)
        elif action == "show_direct":
            await _do_direct(update, result, ai_message, status_msg)
        elif action == "show_trends":
            await _do_trends(update, result, ai_message, status_msg)
        elif action == "list_flights":
            await _do_list(update, ai_message)
        elif action == "remove_flight":
            await _do_remove(update, result, ai_message)
        elif action == "show_latest":
            await _do_latest(update, result, ai_message, status_msg)
        elif action == "show_calendar":
            await _do_calendar(update, result, ai_message, status_msg)
        else:
            await update.message.reply_text(ai_message, parse_mode="HTML")
    except Exception as e:
        logger.error(f"Action '{action}' failed: {e}")
        if status_msg:
            try:
                await status_msg.edit_text(
                    ai_message or "⚠️ İşlem sırasında hata oluştu, tekrar dener misin?",
                    parse_mode="HTML",
                )
            except Exception:
                pass
        elif ai_message:
            await update.message.reply_text(ai_message, parse_mode="HTML")
        else:
            await update.message.reply_text(
                "⚠️ İşlem sırasında hata oluştu, tekrar dener misin?",
            )


async def _do_search(update: Update, context: ContextTypes.DEFAULT_TYPE,
                     result: dict, ai_message: str, status_msg=None):
    origin = _safe_upper(result.get("origin"))
    destination = _safe_upper(result.get("destination"))
    depart_date = (result.get("depart_date") or "").strip()
    return_date = result.get("return_date")
    if return_date in ("null", None, ""):
        return_date = None

    if not origin or not destination or not depart_date:
        if status_msg:
            await status_msg.edit_text(ai_message, parse_mode="HTML")
        else:
            await update.message.reply_text(ai_message, parse_mode="HTML")
        return

    context.user_data["pending_flight"] = {
        "origin": origin,
        "destination": destination,
        "depart_date": depart_date,
        "return_date": return_date,
    }

    price_data = await get_cheapest_prices(origin, destination, depart_date, return_date)

    flight_info = {
        "origin": origin, "destination": destination,
        "depart_date": depart_date, "return_date": return_date,
    }
    card = await format_flight_card(flight_info, price_data)

    final_text = (f"{ai_message}\n\n{card}\n\n"
                  "📌 <b>Bu uçuşu takibe almak ister misin?</b>")
    if status_msg:
        await status_msg.edit_text(
            final_text, parse_mode="HTML",
            reply_markup=_track_keyboard(),
            disable_web_page_preview=True,
        )
    else:
        await update.message.reply_text(
            final_text, parse_mode="HTML",
            reply_markup=_track_keyboard(),
            disable_web_page_preview=True,
        )


async def _do_popular(update: Update, result: dict, ai_message: str, status_msg=None):
    origin = _safe_upper(result.get("origin"))
    if not origin:
        if status_msg:
            await status_msg.edit_text(ai_message, parse_mode="HTML")
        else:
            await update.message.reply_text(ai_message, parse_mode="HTML")
        return

    routes = await get_popular_routes(origin)
    text = await format_popular_routes(routes, origin)
    final = f"{ai_message}\n\n{text}"

    if status_msg:
        await status_msg.edit_text(final, parse_mode="HTML", disable_web_page_preview=True)
    else:
        await update.message.reply_text(final, parse_mode="HTML", disable_web_page_preview=True)


async def _do_direct(update: Update, result: dict, ai_message: str, status_msg=None):
    origin = _safe_upper(result.get("origin"))
    destination = _safe_upper(result.get("destination"))
    month = (result.get("month") or "").strip()

    if not origin or not destination or not month:
        if status_msg:
            await status_msg.edit_text(ai_message, parse_mode="HTML")
        else:
            await update.message.reply_text(ai_message, parse_mode="HTML")
        return

    direct = await get_direct_flights(origin, destination, month)
    text = await format_direct_flights(direct, origin, destination)
    final = f"{ai_message}\n\n{text}"

    if status_msg:
        await status_msg.edit_text(final, parse_mode="HTML", disable_web_page_preview=True)
    else:
        await update.message.reply_text(final, parse_mode="HTML", disable_web_page_preview=True)


async def _do_trends(update: Update, result: dict, ai_message: str, status_msg=None):
    origin = _safe_upper(result.get("origin"))
    destination = _safe_upper(result.get("destination"))
    month = (result.get("month") or "").strip()

    if not origin or not destination or not month:
        if status_msg:
            await status_msg.edit_text(ai_message, parse_mode="HTML")
        else:
            await update.message.reply_text(ai_message, parse_mode="HTML")
        return

    trend = await get_trend_data(origin, destination, month)
    text = format_trend(trend, origin, destination)
    final = f"{ai_message}\n\n{text}"

    if status_msg:
        await status_msg.edit_text(final, parse_mode="HTML", disable_web_page_preview=True)
    else:
        await update.message.reply_text(final, parse_mode="HTML", disable_web_page_preview=True)


async def _do_list(update: Update, ai_message: str):
    user_id = update.effective_user.id
    flights = await get_user_flights(user_id)
    text = format_flight_list(flights)

    await update.message.reply_text(
        f"{ai_message}\n\n{text}",
        parse_mode="HTML",
    )


async def _do_remove(update: Update, result: dict, ai_message: str):
    user_id = update.effective_user.id
    flight_id = result.get("flight_id")

    if not flight_id:
        await update.message.reply_text(ai_message, parse_mode="HTML")
        return

    try:
        flight_id = int(flight_id)
    except (ValueError, TypeError):
        await update.message.reply_text(ai_message, parse_mode="HTML")
        return

    removed = await remove_flight(flight_id, user_id)
    if removed:
        await update.message.reply_text(
            f"✅ #{flight_id} numaralı uçuş takipten çıkarıldı.",
            parse_mode="HTML",
        )
    else:
        await update.message.reply_text(
            f"⚠️ #{flight_id} numaralı uçuş bulunamadı veya sana ait değil.",
            parse_mode="HTML",
        )


async def _do_latest(update: Update, result: dict, ai_message: str, status_msg=None):
    origin = _safe_upper(result.get("origin"))
    destination = _safe_upper(result.get("destination")) or None

    if not origin:
        if status_msg:
            await status_msg.edit_text(ai_message, parse_mode="HTML")
        else:
            await update.message.reply_text(ai_message, parse_mode="HTML")
        return

    prices = await get_latest_prices(origin, destination)
    text = await format_latest_prices(prices, origin)
    final = f"{ai_message}\n\n{text}"

    if status_msg:
        await status_msg.edit_text(final, parse_mode="HTML", disable_web_page_preview=True)
    else:
        await update.message.reply_text(final, parse_mode="HTML", disable_web_page_preview=True)


async def _do_calendar(update: Update, result: dict, ai_message: str, status_msg=None):
    origin = _safe_upper(result.get("origin"))
    dest = _safe_upper(result.get("destination"))
    month = (result.get("month") or "").strip()
    direct_only = bool(result.get("direct"))

    if not origin or not dest or not month:
        if status_msg:
            await status_msg.edit_text(ai_message, parse_mode="HTML")
        else:
            await update.message.reply_text(ai_message, parse_mode="HTML")
        return

    if direct_only:
        raw = await get_direct_flights(origin, dest, month)
        data = [{"date": d["date"], "price": d["price"], "transfers": 0,
                 "duration": d.get("duration", 0)} for d in raw]
    else:
        data = await get_month_matrix(origin, dest, month)
    text = format_calendar(data, origin, dest, month, direct_only)
    final = f"{ai_message}\n\n{text}"

    if status_msg:
        await status_msg.edit_text(final, parse_mode="HTML", disable_web_page_preview=True)
    else:
        await update.message.reply_text(final, parse_mode="HTML", disable_web_page_preview=True)


async def track_yes_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    pending = context.user_data.get("pending_flight")
    if not pending:
        await query.edit_message_text(
            "⚠️ Takip edilecek uçuş bulunamadı. Yeni bir uçuş ara!",
            parse_mode="HTML",
        )
        return

    user_flights = await get_user_flights(query.from_user.id)
    if len(user_flights) >= MAX_TRACKED_FLIGHTS:
        await query.edit_message_text(
            f"⚠️ En fazla <b>{MAX_TRACKED_FLIGHTS}</b> uçuş takip edebilirsin.\n"
            "<i>\"Takiplerimi göster\" yazarak mevcut takiplerini görebilirsin.</i>",
            parse_mode="HTML",
        )
        return

    flight_id = await add_flight(
        query.from_user.id,
        query.message.chat_id,
        pending["origin"],
        pending["destination"],
        pending["depart_date"],
        pending.get("return_date"),
    )
    context.user_data.pop("pending_flight", None)

    if flight_id is None:
        await query.edit_message_text(
            "⚠️ Uçuş eklenemedi, tekrar dener misin?",
            parse_mode="HTML",
        )
        return

    price_data = await get_cheapest_prices(
        pending["origin"], pending["destination"],
        pending["depart_date"], pending.get("return_date"),
    )
    flight = {**pending, "id": flight_id}
    card = await format_flight_card(flight, price_data)

    await query.message.edit_text(
        f"✅ Takibe alındı!\n\n{card}\n\n"
        "📋 <b>Takip nasıl çalışır?</b>\n"
        "• Fiyat %10'dan fazla değişirse anında bildirim\n"
        "• Uçuşa 7 günden az kaldığında günlük kontrol\n"
        "• Her pazartesi haftalık özet rapor\n"
        "• Uçuş tarihi geçince otomatik silinir",
        parse_mode="HTML",
        disable_web_page_preview=True,
    )


async def track_no_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data.pop("pending_flight", None)

    await query.edit_message_text(
        "👍 Tamam! Başka bir şey sormak istersen yaz.",
        parse_mode="HTML",
    )
