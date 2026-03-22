import asyncio
import logging

import httpx

from bot.config import (
    AVIASALES_API_TOKEN, AVIASALES_BASE_URL, CURRENCY,
    PARTNER_MARKER, PARTNER_TRS,
)

logger = logging.getLogger(__name__)

HEADERS = {"X-Access-Token": AVIASALES_API_TOKEN}
API_SEMAPHORE = asyncio.Semaphore(10)


async def _get(client: httpx.AsyncClient, url: str, params: dict) -> dict | None:
    async with API_SEMAPHORE:
        try:
            resp = await client.get(url, params=params, headers=HEADERS, timeout=15)
            if resp.status_code == 429:
                await asyncio.sleep(2)
                resp = await client.get(url, params=params, headers=HEADERS, timeout=15)
            if resp.status_code != 200:
                return None
            return resp.json()
        except httpx.HTTPError as e:
            logger.warning(f"API request failed: {e}")
            return None


async def get_cheapest_prices(origin: str, destination: str,
                              depart_date: str, return_date: str | None = None,
                              client: httpx.AsyncClient | None = None) -> dict | None:
    params = {
        "origin": origin,
        "destination": destination,
        "depart_date": depart_date,
        "currency": CURRENCY,
    }
    if return_date:
        params["return_date"] = return_date

    url = f"{AVIASALES_BASE_URL}/aviasales/v3/prices_for_dates"

    if client:
        data = await _get(client, url, params)
    else:
        async with httpx.AsyncClient() as c:
            data = await _get(c, url, params)

    if not data or not data.get("success") or not data.get("data"):
        return None
    return data["data"][0]


async def get_grouped_prices(origin: str, destination: str,
                             depart_month: str,
                             client: httpx.AsyncClient | None = None) -> list[dict]:
    params = {
        "origin": origin,
        "destination": destination,
        "departure_at": depart_month,
        "group_by": "departure_at",
        "currency": CURRENCY,
    }
    url = f"{AVIASALES_BASE_URL}/aviasales/v3/grouped_prices"

    if client:
        data = await _get(client, url, params)
    else:
        async with httpx.AsyncClient() as c:
            data = await _get(c, url, params)

    if not data or not data.get("success") or not data.get("data"):
        return []

    raw = data["data"]
    if isinstance(raw, dict):
        return list(raw.values())
    return raw


async def get_price_calendar(origin: str, destination: str,
                             depart_month: str,
                             client: httpx.AsyncClient | None = None) -> list[dict]:
    params = {
        "depart_date": depart_month,
        "origin": origin,
        "destination": destination,
        "calendar_type": "departure_date",
        "currency": CURRENCY,
        "token": AVIASALES_API_TOKEN,
    }
    url = f"{AVIASALES_BASE_URL}/v1/prices/calendar"

    if client:
        data = await _get(client, url, params)
    else:
        async with httpx.AsyncClient() as c:
            data = await _get(c, url, params)

    if not data or not data.get("success") or not data.get("data"):
        return []

    raw = data["data"]
    if isinstance(raw, dict):
        return list(raw.values())
    return raw


async def get_price_stats(origin: str, destination: str, month: str,
                          client: httpx.AsyncClient | None = None) -> dict | None:
    prices = await get_grouped_prices(origin, destination, month, client)
    if not prices:
        return None

    price_values = [p["price"] for p in prices if "price" in p]
    if not price_values:
        return None

    direct_prices = [p["price"] for p in prices
                     if "price" in p and p.get("transfers", 1) == 0]

    stats: dict = {
        "min": min(price_values),
        "max": max(price_values),
        "avg": round(sum(price_values) / len(price_values), 2),
        "count": len(price_values),
    }
    if direct_prices:
        stats["direct_min"] = min(direct_prices)

    return stats


async def get_trend_data(origin: str, destination: str, month: str,
                         client: httpx.AsyncClient | None = None) -> list[dict]:
    prices = await get_grouped_prices(origin, destination, month, client)
    if not prices:
        return []

    trend = []
    for p in sorted(prices, key=lambda x: x.get("departure_at", "")):
        dep = p.get("departure_at", "")
        date_str = dep[:10] if dep else ""
        trend.append({
            "date": date_str,
            "price": p.get("price", 0),
            "transfers": p.get("transfers", 0),
            "airline": p.get("airline", ""),
            "duration": p.get("duration", 0),
        })
    return trend


async def get_popular_routes(origin: str,
                             client: httpx.AsyncClient | None = None) -> list[dict]:
    params = {
        "origin": origin,
        "currency": CURRENCY,
        "sorting": "price",
        "unique": "true",
        "limit": "10",
    }
    url = f"{AVIASALES_BASE_URL}/aviasales/v3/prices_for_dates"

    if client:
        data = await _get(client, url, params)
    else:
        async with httpx.AsyncClient() as c:
            data = await _get(c, url, params)

    if not data or not data.get("success") or not data.get("data"):
        return []

    routes = []
    for p in data["data"]:
        routes.append({
            "destination": p.get("destination", ""),
            "price": p.get("price", 0),
            "transfers": p.get("transfers", 0),
            "airline": p.get("airline", ""),
            "departure_at": (p.get("departure_at") or "")[:10],
            "return_at": (p.get("return_at") or "")[:10],
            "link": p.get("link", ""),
        })
    return routes


async def get_direct_flights(origin: str, destination: str,
                             depart_month: str,
                             client: httpx.AsyncClient | None = None) -> list[dict]:
    params = {
        "origin": origin,
        "destination": destination,
        "departure_at": depart_month,
        "group_by": "departure_at",
        "currency": CURRENCY,
        "direct": "true",
    }
    url = f"{AVIASALES_BASE_URL}/aviasales/v3/grouped_prices"

    if client:
        data = await _get(client, url, params)
    else:
        async with httpx.AsyncClient() as c:
            data = await _get(c, url, params)

    if not data or not data.get("success") or not data.get("data"):
        return []

    raw = data["data"]
    items = list(raw.values()) if isinstance(raw, dict) else raw

    results = []
    for p in sorted(items, key=lambda x: x.get("departure_at", "")):
        dep = p.get("departure_at", "")
        results.append({
            "date": dep[:10] if dep else "",
            "price": p.get("price", 0),
            "airline": p.get("airline", ""),
            "duration": p.get("duration", 0),
            "link": p.get("link", ""),
        })
    return results


async def batch_fetch_prices(routes: list[tuple[str, str, str, str | None]],
                             client: httpx.AsyncClient) -> dict:
    cache: dict[str, dict | None] = {}

    async def _fetch_one(key: str, origin: str, dest: str,
                         depart: str, ret: str | None):
        cache[key] = await get_cheapest_prices(origin, dest, depart, ret, client)

    tasks = []
    for origin, dest, depart, ret in routes:
        key = f"{origin}-{dest}-{depart}-{ret or ''}"
        if key not in cache:
            cache[key] = None
            tasks.append(_fetch_one(key, origin, dest, depart, ret))

    await asyncio.gather(*tasks)
    return cache


async def batch_fetch_stats(route_months: list[tuple[str, str, str]],
                            client: httpx.AsyncClient) -> dict:
    cache: dict[str, dict | None] = {}

    async def _fetch_one(key: str, origin: str, dest: str, month: str):
        cache[key] = await get_price_stats(origin, dest, month, client)

    tasks = []
    for origin, dest, month in route_months:
        key = f"{origin}-{dest}-{month}"
        if key not in cache:
            cache[key] = None
            tasks.append(_fetch_one(key, origin, dest, month))

    await asyncio.gather(*tasks)
    return cache


async def create_partner_link(url: str, sub_id: str = "bot") -> str:
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{AVIASALES_BASE_URL}/links/v1/create",
                headers={"X-Access-Token": AVIASALES_API_TOKEN},
                json={
                    "trs": int(PARTNER_TRS),
                    "marker": int(PARTNER_MARKER),
                    "shorten": True,
                    "links": [{"url": url, "sub_id": sub_id}],
                },
                timeout=10,
            )
            if resp.status_code == 200:
                data = resp.json()
                links = data.get("result", {}).get("links", [])
                if links and links[0].get("code") == "success":
                    return links[0]["partner_url"]
    except Exception as e:
        logger.warning(f"Partner link creation failed: {e}")

    return url


def _raw_aviasales_url(link_path: str) -> str:
    base = f"https://www.aviasales.com{link_path}"
    sep = "&" if "?" in link_path else "?"
    return f"{base}{sep}currency=try&locale=tr"


def _to_ddmm(date_str: str) -> str:
    parts = date_str.split("-")
    return f"{parts[2]}{parts[1]}"


def _raw_search_url(origin: str, destination: str, depart_date: str,
                    return_date: str | None = None) -> str:
    path = f"{origin}{_to_ddmm(depart_date)}{destination}"
    if return_date:
        path += _to_ddmm(return_date)
    return f"https://www.aviasales.com/search/{path}1?currency=try&locale=tr"


async def build_purchase_link(link_path: str, sub_id: str = "bot") -> str:
    if not link_path:
        return ""
    url = _raw_aviasales_url(link_path)
    return await create_partner_link(url, sub_id)


async def build_search_link(origin: str, destination: str, depart_date: str,
                            return_date: str | None = None,
                            sub_id: str = "bot") -> str:
    url = _raw_search_url(origin, destination, depart_date, return_date)
    return await create_partner_link(url, sub_id)
