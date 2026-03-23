import asyncio
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
    get_calendar_prices,
)
from bot.services.database import (
    add_flight, get_user_flights, remove_flight, upsert_user,
    get_user_email, save_user_email,
)
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


def _track_keyboard(origin: str, dest: str, depart: str,
                     return_date: str | None = None) -> InlineKeyboardMarkup:
    ret = return_date or ""
    data = f"track:{origin}:{dest}:{depart}:{ret}"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Takibe Al", callback_data=data)],
        [InlineKeyboardButton("❌ Hayır", callback_data="ai_track_no")],
    ])


def _append_cheapest_to_history(context, data: list[dict], origin: str, dest: str,
                                direct: bool = False):
    if not data:
        return
    valid = [d for d in data if d.get("price", 0) > 0]
    if not valid:
        return
    cheapest = min(valid, key=lambda d: d["price"])
    if direct:
        note = (f"[Takvim sonucu (AKTARMASIZ): {origin}→{dest}, "
                f"en ucuz gün {cheapest['date']} — {cheapest['price']:,}₺. "
                f"Bu sonuçlar aktarmasız uçuşlar için. Kullanıcı bu sonuçlardan bilet detayı isterse "
                f"search_flight ile direct=true kullan!]")
    else:
        note = (f"[Takvim sonucu: {origin}→{dest}, "
                f"en ucuz gün {cheapest['date']} — {cheapest['price']:,}₺]")
    history = context.user_data.get("chat_history", [])
    if history and history[-1]["role"] == "assistant":
        history[-1]["text"] += f"\n{note}"


SEARCH_STATUS = {
    "search_flight": "🔍 Uçuş fiyatlarına bakıyorum...",
    "show_popular": "🌍 Popüler rotaları araştırıyorum...",
    "show_direct": "✈️ Aktarmasız uçuşlara bakıyorum...",
    "show_trends": "📈 Fiyat trendlerini inceliyorum...",
    "show_latest": "🔥 Son bulunan biletleri getiriyorum...",
    "show_calendar": "📅 Fiyat takvimini hazırlıyorum...",
}


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    import time as _time
    t0 = _time.monotonic()

    text = update.message.text.strip()
    if not text:
        return

    if await handle_email_reply(update, context):
        return

    history = context.user_data.get("chat_history", [])

    user = update.effective_user
    await upsert_user(user.id, user.username)
    logger.info(f"⏱ db: {_time.monotonic() - t0:.2f}s | hist={len(history)}")

    thinking_msg = await update.message.reply_text("💭 Düşünüyorum...")

    t1 = _time.monotonic()
    try:
        result = await gemini_chat(text, history)
    except Exception as e:
        logger.error(f"AI chat error: {e}")
        await thinking_msg.edit_text(
            "⚠️ Bir hata oluştu, tekrar dener misin?",
            parse_mode="HTML",
        )
        return
    t2 = _time.monotonic()
    logger.info(f"⏱ ai: {t2 - t1:.2f}s")

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
    if status_text:
        await thinking_msg.edit_text(
            f"{ai_message}\n\n{status_text}",
            parse_mode="HTML",
        )

    try:
        if action == "search_flight":
            await _do_search(update, context, result, ai_message, thinking_msg)
        elif action == "show_popular":
            await _do_popular(update, result, ai_message, thinking_msg)
        elif action == "show_direct":
            await _do_direct(update, context, result, ai_message, thinking_msg)
        elif action == "show_trends":
            await _do_trends(update, result, ai_message, thinking_msg)
        elif action == "list_flights":
            await thinking_msg.edit_text(
                f"{ai_message}\n\n{await _build_list_text(update)}",
                parse_mode="HTML",
            )
        elif action == "remove_flight":
            await _do_remove(update, result, ai_message, thinking_msg)
        elif action == "show_latest":
            await _do_latest(update, result, ai_message, thinking_msg)
        elif action == "show_calendar":
            await _do_calendar(update, context, result, ai_message, thinking_msg)
        else:
            await thinking_msg.edit_text(ai_message, parse_mode="HTML")
    except Exception as e:
        logger.error(f"Action '{action}' failed: {e}")
        try:
            await thinking_msg.edit_text(
                ai_message or "⚠️ İşlem sırasında hata oluştu, tekrar dener misin?",
                parse_mode="HTML",
            )
        except Exception:
            pass

    logger.info(f"⏱ TOTAL: {_time.monotonic() - t0:.2f}s | action={action} | api: {_time.monotonic() - t2:.2f}s")


async def _do_search(update: Update, context: ContextTypes.DEFAULT_TYPE,
                     result: dict, ai_message: str, status_msg=None):
    origin = _safe_upper(result.get("origin"))
    destination = _safe_upper(result.get("destination"))
    depart_date = (result.get("depart_date") or "").strip()
    return_date = result.get("return_date")
    direct = bool(result.get("direct"))
    if return_date in ("null", None, ""):
        return_date = None

    if not origin or not destination or not depart_date:
        if status_msg:
            await status_msg.edit_text(ai_message, parse_mode="HTML")
        else:
            await update.message.reply_text(ai_message, parse_mode="HTML")
        return

    month = depart_date[:7]
    price_data, month_prices = await asyncio.gather(
        get_cheapest_prices(origin, destination, depart_date, return_date, direct=direct),
        get_calendar_prices(origin, destination, month, direct=direct),
    )

    stats = None
    if month_prices:
        valid = [d["price"] for d in month_prices if d.get("price", 0) > 0]
        if valid:
            stats = {"avg": sum(valid) / len(valid)}

    flight_info = {
        "origin": origin, "destination": destination,
        "depart_date": depart_date, "return_date": return_date,
    }
    card = await format_flight_card(flight_info, price_data, stats=stats)

    final_text = (f"{ai_message}\n\n{card}\n\n"
                  "📌 <b>Bu uçuşu takibe almak ister misin?</b>")
    kb = _track_keyboard(origin, destination, depart_date, return_date)
    if status_msg:
        await status_msg.edit_text(
            final_text, parse_mode="HTML",
            reply_markup=kb,
            disable_web_page_preview=True,
        )
    else:
        await update.message.reply_text(
            final_text, parse_mode="HTML",
            reply_markup=kb,
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


async def _do_direct(update: Update, context: ContextTypes.DEFAULT_TYPE,
                     result: dict, ai_message: str, status_msg=None):
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

    _append_cheapest_to_history(context, direct, origin, destination, direct=True)

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


async def _build_list_text(update: Update) -> str:
    user_id = update.effective_user.id
    flights = await get_user_flights(user_id)
    return format_flight_list(flights)


async def _do_remove(update: Update, result: dict, ai_message: str, status_msg=None):
    user_id = update.effective_user.id
    flight_id = result.get("flight_id")

    if not flight_id:
        if status_msg:
            await status_msg.edit_text(ai_message, parse_mode="HTML")
        else:
            await update.message.reply_text(ai_message, parse_mode="HTML")
        return

    try:
        flight_id = int(flight_id)
    except (ValueError, TypeError):
        if status_msg:
            await status_msg.edit_text(ai_message, parse_mode="HTML")
        else:
            await update.message.reply_text(ai_message, parse_mode="HTML")
        return

    removed = await remove_flight(flight_id, user_id)
    msg = (f"✅ #{flight_id} numaralı uçuş takipten çıkarıldı."
           if removed else
           f"⚠️ #{flight_id} numaralı uçuş bulunamadı veya sana ait değil.")
    if status_msg:
        await status_msg.edit_text(msg, parse_mode="HTML")
    else:
        await update.message.reply_text(msg, parse_mode="HTML")


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


async def _do_calendar(update: Update, context: ContextTypes.DEFAULT_TYPE,
                       result: dict, ai_message: str, status_msg=None):
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

    data = await get_calendar_prices(origin, dest, month, direct=direct_only)
    text = format_calendar(data, origin, dest, month, direct_only)
    final = f"{ai_message}\n\n{text}"

    _append_cheapest_to_history(context, data, origin, dest, direct_only)

    if status_msg:
        await status_msg.edit_text(final, parse_mode="HTML", disable_web_page_preview=True)
    else:
        await update.message.reply_text(final, parse_mode="HTML", disable_web_page_preview=True)


async def track_yes_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    try:
        await query.answer()
    except Exception:
        pass

    parts = (query.data or "").split(":")
    if len(parts) < 4:
        await query.edit_message_text(
            "⚠️ Takip edilecek uçuş bulunamadı. Yeni bir uçuş ara!",
            parse_mode="HTML",
        )
        return

    origin = parts[1].upper()
    dest = parts[2].upper()
    depart_date = parts[3]
    return_date = parts[4] if len(parts) > 4 and parts[4] else None

    try:
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
            origin, dest, depart_date, return_date,
        )

        if flight_id is None:
            await query.edit_message_text(
                "⚠️ Uçuş eklenemedi, tekrar dener misin?",
                parse_mode="HTML",
            )
            return

        email = await get_user_email(query.from_user.id)

        ret_text = f"\n📅 Dönüş: <b>{return_date}</b>" if return_date else ""
        track_text = (
            f"✅ Takibe alındı!\n\n"
            f"✈️ <b>{origin} → {dest}</b>\n"
            f"📅 Gidiş: <b>{depart_date}</b>{ret_text}\n\n"
            "📋 <b>Takip nasıl çalışır?</b>\n"
            "• Fiyat %10'dan fazla değişirse anında bildirim\n"
            "• Uçuşa 7 günden az kaldığında günlük kontrol\n"
            "• Her pazartesi haftalık özet rapor\n"
            "• Uçuş tarihi geçince otomatik silinir"
        )

        if not email:
            track_text += (
                "\n\n📧 <b>Fiyat düşünce e-posta da gönderelim mi?</b>\n"
                "E-posta adresini yaz, bildirimleri oraya da yollayalım.\n"
                "<i>Atlamak için herhangi bir şey yaz.</i>"
            )
            context.user_data["awaiting_email"] = True

        await query.message.edit_text(
            track_text,
            parse_mode="HTML",
            disable_web_page_preview=True,
        )
    except Exception as e:
        logger.error(f"track_yes_callback error: {e}", exc_info=True)
        try:
            await query.message.edit_text(
                "⚠️ Bir hata oluştu, tekrar dener misin?",
                parse_mode="HTML",
            )
        except Exception:
            pass


async def handle_email_reply(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    if not context.user_data.get("awaiting_email"):
        return False

    context.user_data.pop("awaiting_email", None)
    text = update.message.text.strip()

    if re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', text):
        await save_user_email(update.effective_user.id, text)
        await update.message.reply_text(
            f"✅ E-posta kaydedildi: <b>{text}</b>\n"
            "Fiyat değişikliklerinde seni bilgilendireceğiz!",
            parse_mode="HTML",
        )
    else:
        await update.message.reply_text(
            "👍 Tamam, e-posta atlandı. Başka bir şey sormak istersen yaz!",
            parse_mode="HTML",
        )
    return True


async def track_no_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data.pop("pending_flight", None)

    await query.edit_message_text(
        "👍 Tamam! Başka bir şey sormak istersen yaz.",
        parse_mode="HTML",
    )
