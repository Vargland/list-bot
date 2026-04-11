import os
import asyncpg
import asyncio

_pool = None


async def get_pool():
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(os.environ["DATABASE_URL"])
    return _pool


async def init_db():
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS items (
                id SERIAL PRIMARY KEY,
                chat_id BIGINT NOT NULL,
                item TEXT NOT NULL,
                bought BOOLEAN NOT NULL DEFAULT FALSE,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)


async def add_items(chat_id: int, items: list[str]):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.executemany(
            "INSERT INTO items (chat_id, item, bought) VALUES ($1, $2, FALSE)",
            [(chat_id, item.strip()) for item in items if item.strip()]
        )


async def get_items(chat_id: int, only_pending=True) -> list[str]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        if only_pending:
            rows = await conn.fetch(
                "SELECT item FROM items WHERE chat_id = $1 AND bought = FALSE ORDER BY added_at",
                chat_id
            )
        else:
            rows = await conn.fetch(
                "SELECT item FROM items WHERE chat_id = $1 ORDER BY added_at",
                chat_id
            )
    return [row["item"] for row in rows]


async def mark_bought(chat_id: int, items_to_mark: list[str]) -> list[str]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        for item in items_to_mark:
            await conn.execute(
                "UPDATE items SET bought = TRUE WHERE chat_id = $1 AND LOWER(item) = LOWER($2)",
                chat_id, item.strip()
            )
    return await get_items(chat_id, only_pending=True)


async def clear_bought(chat_id: int):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM items WHERE chat_id = $1 AND bought = TRUE", chat_id)


async def clear_all(chat_id: int):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM items WHERE chat_id = $1", chat_id)
