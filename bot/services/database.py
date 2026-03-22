import aiosqlite
from bot.config import DB_PATH


async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS tracked_flights (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                chat_id INTEGER NOT NULL,
                origin TEXT NOT NULL,
                destination TEXT NOT NULL,
                depart_date TEXT NOT NULL,
                return_date TEXT,
                last_price REAL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_user_id ON tracked_flights(user_id)
        """)
        await db.commit()


async def add_flight(user_id: int, chat_id: int, origin: str, destination: str,
                     depart_date: str, return_date: str | None = None) -> int | None:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "SELECT COUNT(*) FROM tracked_flights WHERE user_id = ?",
            (user_id,)
        )
        row = await cursor.fetchone()
        if row and row[0] >= 3:
            return None

        cursor = await db.execute(
            """INSERT INTO tracked_flights
               (user_id, chat_id, origin, destination, depart_date, return_date)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (user_id, chat_id, origin.upper(), destination.upper(),
             depart_date, return_date)
        )
        await db.commit()
        return cursor.lastrowid


async def remove_flight(user_id: int, flight_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute(
            "DELETE FROM tracked_flights WHERE id = ? AND user_id = ?",
            (flight_id, user_id)
        )
        await db.commit()
        return cursor.rowcount > 0


async def get_user_flights(user_id: int) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM tracked_flights WHERE user_id = ? ORDER BY created_at",
            (user_id,)
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


async def get_all_tracked_flights() -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute("SELECT * FROM tracked_flights")
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


async def update_last_price(flight_id: int, price: float):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE tracked_flights SET last_price = ? WHERE id = ?",
            (price, flight_id)
        )
        await db.commit()
