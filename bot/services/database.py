import asyncpg
from bot.config import DATABASE_URL

_pool: asyncpg.Pool | None = None


async def _get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(DATABASE_URL, min_size=2, max_size=10)
    return _pool


async def init_db():
    pool = await _get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS tracked_flights (
                id SERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL,
                chat_id BIGINT NOT NULL,
                origin TEXT NOT NULL,
                destination TEXT NOT NULL,
                depart_date TEXT NOT NULL,
                return_date TEXT,
                last_price DOUBLE PRECISION,
                created_at TIMESTAMPTZ DEFAULT NOW()
            )
        """)
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_user_id ON tracked_flights(user_id)
        """)


async def add_flight(user_id: int, chat_id: int, origin: str, destination: str,
                     depart_date: str, return_date: str | None = None) -> int | None:
    pool = await _get_pool()
    async with pool.acquire() as conn:
        count = await conn.fetchval(
            "SELECT COUNT(*) FROM tracked_flights WHERE user_id = $1",
            user_id,
        )
        if count >= 3:
            return None

        row = await conn.fetchrow(
            """INSERT INTO tracked_flights
               (user_id, chat_id, origin, destination, depart_date, return_date)
               VALUES ($1, $2, $3, $4, $5, $6)
               RETURNING id""",
            user_id, chat_id, origin.upper(), destination.upper(),
            depart_date, return_date,
        )
        return row["id"] if row else None


async def remove_flight(flight_id: int, user_id: int) -> bool:
    pool = await _get_pool()
    async with pool.acquire() as conn:
        result = await conn.execute(
            "DELETE FROM tracked_flights WHERE id = $1 AND user_id = $2",
            flight_id, user_id,
        )
        return result.split()[-1] != "0"


async def get_user_flights(user_id: int) -> list[dict]:
    pool = await _get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM tracked_flights WHERE user_id = $1 ORDER BY created_at",
            user_id,
        )
        return [dict(r) for r in rows]


async def get_all_tracked_flights() -> list[dict]:
    pool = await _get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT * FROM tracked_flights")
        return [dict(r) for r in rows]


async def update_last_price(flight_id: int, price: float):
    pool = await _get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE tracked_flights SET last_price = $1 WHERE id = $2",
            price, flight_id,
        )
