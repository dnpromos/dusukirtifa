from bot.services.airlines import get_airline_name
from bot.services.aviasales import build_search_link, build_purchase_link


def _format_stops(transfers: int) -> str:
    if transfers == 0:
        return "Aktarmasız"
    elif transfers == 1:
        return "1 aktarma"
    return f"{transfers} aktarma"


def _format_duration(minutes: int) -> str:
    if not minutes:
        return ""
    h, m = divmod(minutes, 60)
    return f"{h}sa {m}dk"


async def format_flight_card(flight: dict, price_data: dict | None = None,
                             stats: dict | None = None) -> str:
    origin = flight["origin"]
    dest = flight["destination"]
    depart = flight["depart_date"]
    ret = flight.get("return_date")

    lines = [
        f"✈️ <b>{origin} → {dest}</b>",
        f"📅 Gidiş: <b>{depart}</b>",
    ]
    if ret:
        lines.append(f"📅 Dönüş: <b>{ret}</b>")

    if price_data:
        price = price_data.get("price", "—")
        airline_code = price_data.get("airline", "")
        airline_name = get_airline_name(airline_code)
        transfers = price_data.get("transfers", -1)
        duration = price_data.get("duration", 0)

        lines.append(f"💰 Güncel fiyat: <b>{price:,} ₺</b>")
        if airline_name:
            lines.append(f"🏷 Havayolu: <b>{airline_name}</b>")
        if transfers >= 0:
            lines.append(f"🔄 {_format_stops(transfers)}")
        if duration:
            lines.append(f"⏱ Süre: {_format_duration(duration)}")

    old_price = flight.get("last_price")
    if old_price and price_data and price_data.get("price"):
        diff = price_data["price"] - old_price
        if diff < 0:
            lines.append(f"📉 Fiyat düştü: <b>{abs(diff):,.0f} ₺</b> indirim!")
        elif diff > 0:
            lines.append(f"📈 Fiyat arttı: <b>{diff:,.0f} ₺</b> artış")
        else:
            lines.append("➡️ Fiyat değişmedi")

    if stats:
        lines.append("")
        lines.append("📊 <b>Aylık İstatistikler:</b>")
        lines.append(f"   En düşük: {stats['min']:,} ₺")
        lines.append(f"   En yüksek: {stats['max']:,} ₺")
        lines.append(f"   Ortalama: {stats['avg']:,.2f} ₺")
        if stats.get("direct_min"):
            lines.append(f"   Aktarmasız en düşük: {stats['direct_min']:,} ₺")
        lines.append(f"   Bulunan bilet: {stats['count']}")

    purchase_url = await build_search_link(origin, dest, depart, ret, sub_id="card")
    lines.append(f"\n🛒 <a href='{purchase_url}'>Şimdi Satın Al</a>")

    return "\n".join(lines)


def format_trend(trend_data: list[dict], origin: str, dest: str) -> str:
    if not trend_data:
        return "📭 Bu rota için fiyat trendi bulunamadı."

    lines = [f"📈 <b>Fiyat Trendi: {origin} → {dest}</b>\n"]

    for t in trend_data[:15]:
        date = t["date"]
        price = t["price"]
        transfers = t.get("transfers", 0)
        airline_code = t.get("airline", "")
        airline_name = get_airline_name(airline_code)
        stop_str = _format_stops(transfers)
        duration = _format_duration(t.get("duration", 0))

        line = f"  📅 {date}  —  <b>{price:,} ₺</b>"
        details = []
        if airline_name:
            details.append(airline_name)
        details.append(stop_str)
        if duration:
            details.append(duration)
        line += f"\n       {' · '.join(details)}"
        lines.append(line)

    return "\n".join(lines)


async def format_popular_routes(routes: list[dict], origin: str) -> str:
    if not routes:
        return f"📭 <b>{origin}</b> için popüler rota bulunamadı."

    lines = [f"🌍 <b>{origin} çıkışlı Popüler Rotalar</b>\n"]

    for i, r in enumerate(routes, 1):
        dest = r["destination"]
        price = r["price"]
        airline_name = get_airline_name(r.get("airline", ""))
        stops = _format_stops(r.get("transfers", 0))
        dep = r.get("departure_at", "")
        ret = r.get("return_at", "")

        line = f"  {i}. <b>{origin} → {dest}</b> — <b>{price:,} ₺</b>"
        details = []
        if airline_name:
            details.append(airline_name)
        details.append(stops)
        if dep:
            date_info = f"📅 {dep}"
            if ret:
                date_info += f" ↩ {ret}"
            details.append(date_info)
        line += f"\n      {' · '.join(details)}"

        link = r.get("link", "")
        if link:
            purchase_url = await build_purchase_link(link, sub_id="popular")
            line += f"\n      🛒 <a href='{purchase_url}'>Satın Al</a>"

        lines.append(line)

    return "\n".join(lines)


async def format_direct_flights(flights: list[dict], origin: str, dest: str) -> str:
    if not flights:
        return (f"📭 <b>{origin} → {dest}</b> için aktarmasız uçuş bulunamadı.\n"
                "Bu rotada direkt sefer olmayabilir.")

    prices = [f["price"] for f in flights if f.get("price", 0) > 0]
    min_price = min(prices) if prices else 0

    lines = [f"✈️ <b>Aktarmasız Uçuşlar: {origin} → {dest}</b>\n"]

    for f in flights:
        date = f["date"]
        price = f["price"]
        if price <= 0:
            continue

        day_month = f"{date[8:10]}.{date[5:7]}" if len(date) >= 10 else date
        star = " ⭐" if price == min_price else ""
        airline_name = get_airline_name(f.get("airline", ""))
        duration = _format_duration(f.get("duration", 0))

        details = []
        if airline_name:
            details.append(airline_name)
        if duration:
            details.append(duration)
        detail_str = f" · {' · '.join(details)}" if details else ""

        lines.append(f"  {day_month} — <b>{price:,}₺</b> ✈️{detail_str}{star}")

    if min_price:
        lines.append(f"\n⭐ En ucuz gün: <b>{min_price:,}₺</b>")

    return "\n".join(lines)


async def format_latest_prices(prices: list[dict], origin: str) -> str:
    if not prices:
        return f"📭 <b>{origin}</b> çıkışlı güncel bilet bulunamadı."

    lines = [f"🔥 <b>{origin} — Son Bulunan En Ucuz Biletler</b>\n"]

    for i, p in enumerate(prices, 1):
        dest = p["destination"]
        price = p["price"]
        depart = p.get("depart_date", "")[:10]
        ret = p.get("return_date", "")[:10]
        airline_name = get_airline_name(p.get("airline", ""))
        stops = _format_stops(p.get("transfers", 0))

        line = f"  {i}. <b>{origin} → {dest}</b> — <b>{price:,}₺</b>"
        details = []
        if airline_name:
            details.append(airline_name)
        details.append(stops)
        if depart:
            date_info = f"📅 {depart}"
            if ret:
                date_info += f" ↩ {ret}"
            details.append(date_info)
        line += f"\n      {' · '.join(details)}"

        if depart:
            url = await build_search_link(origin, dest, depart, ret or None, sub_id="latest")
            line += f"\n      🛒 <a href='{url}'>Satın Al</a>"

        lines.append(line)

    return "\n".join(lines)


def format_calendar(data: list[dict], origin: str, dest: str, month: str,
                    direct_only: bool = False) -> str:
    label = " — Aktarmasız" if direct_only else ""
    if not data:
        if direct_only:
            return f"📭 <b>{origin} → {dest}</b> için {month} aktarmasız uçuş bulunamadı."
        return f"📭 <b>{origin} → {dest}</b> için {month} takvimi bulunamadı."

    prices = [d["price"] for d in data if d["price"] > 0]
    min_price = min(prices) if prices else 0

    lines = [f"📅 <b>Fiyat Takvimi: {origin} → {dest} ({month}){label}</b>\n"]

    for d in data:
        date = d["date"]
        price = d["price"]
        if price <= 0:
            continue

        day_month = f"{date[8:10]}.{date[5:7]}" if len(date) >= 10 else date
        star = " ⭐" if price == min_price else ""
        transfers = d.get("transfers", 0)
        stop_str = "✈️" if transfers == 0 else f"🔄{transfers}"

        lines.append(f"  {day_month} — <b>{price:,}₺</b> {stop_str}{star}")

    if min_price:
        lines.append(f"\n⭐ En ucuz gün: <b>{min_price:,}₺</b>")

    return "\n".join(lines)


async def format_smart_alert(flight: dict, price_data: dict,
                             diff: float, days_until: int) -> str:
    origin = flight["origin"]
    dest = flight["destination"]
    depart = flight["depart_date"]
    new_price = price_data["price"]
    lowest = flight.get("lowest_price")

    if diff < 0:
        emoji = "📉"
        change = f"<b>{abs(diff):,.0f}₺ düştü!</b>"
    else:
        emoji = "📈"
        change = f"<b>{diff:,.0f}₺ arttı</b>"

    lines = [
        f"{emoji} <b>{origin} → {dest}</b> ({depart})",
        f"💰 Fiyat: <b>{new_price:,.0f}₺</b> ({change})",
    ]

    if lowest:
        lines.append(f"⭐ En düşük: {lowest:,.0f}₺")

    if days_until <= 7:
        lines.append(f"⚡ <b>Uçuşa {days_until} gün kaldı!</b>")
    elif days_until <= 14:
        lines.append(f"⏰ Uçuşa {days_until} gün kaldı")

    url = await build_search_link(origin, dest, depart, flight.get("return_date"), sub_id="alert")
    lines.append(f"🛒 <a href='{url}'>Satın Al</a>")

    return "\n".join(lines)


def format_flight_list(flights: list[dict]) -> str:
    if not flights:
        return "📭 Henüz takip ettiğiniz uçuş yok."

    lines = ["📋 <b>Takip ettiğiniz uçuşlar:</b>\n"]
    for i, f in enumerate(flights, 1):
        ret_str = f" ↩ {f['return_date']}" if f.get("return_date") else ""
        price_str = f" — Son fiyat: {f['last_price']:,.0f} ₺" if f.get("last_price") else ""
        lines.append(
            f"  {i}. <b>{f['origin']} → {f['destination']}</b>\n"
            f"     📅 {f['depart_date']}{ret_str}{price_str}\n"
            f"     🆔 ID: <code>{f['id']}</code>"
        )
    return "\n".join(lines)
