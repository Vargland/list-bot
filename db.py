import os
import asyncpg

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
            CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT NOT NULL,
                chat_id BIGINT NOT NULL,
                name TEXT NOT NULL,
                PRIMARY KEY (user_id, chat_id)
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS items (
                id SERIAL PRIMARY KEY,
                chat_id BIGINT NOT NULL,
                user_id BIGINT,
                item TEXT NOT NULL,
                bought BOOLEAN NOT NULL DEFAULT FALSE,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        # Migración: agrega columna user_id si la tabla ya existía sin ella
        await conn.execute("""
            ALTER TABLE items ADD COLUMN IF NOT EXISTS user_id BIGINT
        """)


# --- Usuarios ---

async def get_user_name(user_id: int, chat_id: int) -> str | None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT name FROM users WHERE user_id = $1 AND chat_id = $2",
            user_id, chat_id
        )
    return row["name"] if row else None


async def register_user(user_id: int, chat_id: int, name: str):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO users (user_id, chat_id, name) VALUES ($1, $2, $3)
            ON CONFLICT (user_id, chat_id) DO UPDATE SET name = $3
            """,
            user_id, chat_id, name.strip()
        )


# --- Items ---

async def add_items(chat_id: int, user_id: int, items: list[str]):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.executemany(
            "INSERT INTO items (chat_id, user_id, item, bought) VALUES ($1, $2, $3, FALSE)",
            [(chat_id, user_id, item.strip()) for item in items if item.strip()]
        )


async def get_items(chat_id: int, only_pending=True) -> list[dict]:
    """Devuelve lista de dicts con 'item' y 'name' del usuario que lo agregó."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        if only_pending:
            rows = await conn.fetch(
                """
                SELECT i.item, u.name
                FROM items i
                JOIN users u ON i.user_id = u.user_id AND i.chat_id = u.chat_id
                WHERE i.chat_id = $1 AND i.bought = FALSE
                ORDER BY i.added_at
                """,
                chat_id
            )
        else:
            rows = await conn.fetch(
                """
                SELECT i.item, u.name
                FROM items i
                JOIN users u ON i.user_id = u.user_id AND i.chat_id = u.chat_id
                WHERE i.chat_id = $1
                ORDER BY i.added_at
                """,
                chat_id
            )
    return [{"item": row["item"], "name": row["name"]} for row in rows]


async def mark_bought(chat_id: int, items_to_mark: list[str]) -> list[dict]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        for item in items_to_mark:
            await conn.execute(
                "UPDATE items SET bought = TRUE WHERE chat_id = $1 AND LOWER(item) = LOWER($2) AND bought = FALSE",
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


async def delete_item(chat_id: int, item_name: str) -> bool:
    """Borra un item pendiente. Devuelve True si se encontró y borró."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        result = await conn.execute(
            "DELETE FROM items WHERE chat_id = $1 AND LOWER(item) = LOWER($2) AND bought = FALSE",
            chat_id, item_name.strip()
        )
    return result != "DELETE 0"


async def edit_item(chat_id: int, old_name: str, new_name: str) -> bool:
    """Renombra un item pendiente. Devuelve True si se encontró y editó."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        result = await conn.execute(
            "UPDATE items SET item = $3 WHERE chat_id = $1 AND LOWER(item) = LOWER($2) AND bought = FALSE",
            chat_id, old_name.strip(), new_name.strip()
        )
    return result != "UPDATE 0"
