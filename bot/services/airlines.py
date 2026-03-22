import logging

import httpx

from bot.config import AVIASALES_API_TOKEN, AVIASALES_BASE_URL

logger = logging.getLogger(__name__)

_airline_cache: dict[str, str] = {}


async def load_airlines():
    global _airline_cache
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{AVIASALES_BASE_URL}/data/en/airlines.json",
                params={"token": AVIASALES_API_TOKEN},
                timeout=15,
            )
            if resp.status_code == 200:
                data = resp.json()
                for airline in data:
                    code = airline.get("iata_code") or airline.get("code", "")
                    name = airline.get("name", "")
                    if code and name:
                        _airline_cache[code] = name
                logger.info(f"Loaded {len(_airline_cache)} airlines")
    except Exception as e:
        logger.warning(f"Failed to load airlines: {e}")


def get_airline_name(code: str) -> str:
    if not code:
        return ""
    return _airline_cache.get(code, code)
