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

    lines = [f"✈️ <b>Aktarmasız Uçuşlar: {origin} → {dest}</b>\n"]

    for f in flights[:15]:
        date = f["date"]
        price = f["price"]
        airline_name = get_airline_name(f.get("airline", ""))
        duration = _format_duration(f.get("duration", 0))

        line = f"  📅 {date}  —  <b>{price:,} ₺</b>"
        details = []
        if airline_name:
            details.append(airline_name)
        if duration:
            details.append(duration)
        line += f"\n       {' · '.join(details)}"

        link = f.get("link", "")
        if link:
            purchase_url = await build_purchase_link(link, sub_id="direct")
            line += f"  <a href='{purchase_url}'>Satın Al</a>"

        lines.append(line)

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
