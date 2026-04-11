import os
import psycopg2
import psycopg2.extras
from urllib.parse import urlparse

def get_conn():
    db_url = os.environ["DATABASE_URL"]
    conn = psycopg2.connect(db_url)
    return conn


def init_db():
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS items (
                    id SERIAL PRIMARY KEY,
                    chat_id BIGINT NOT NULL,
                    item TEXT NOT NULL,
                    bought BOOLEAN NOT NULL DEFAULT FALSE,
                    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
        conn.commit()


def add_items(chat_id: int, items: list[str]):
    with get_conn() as conn:
        with conn.cursor() as cur:
            psycopg2.extras.execute_batch(
                cur,
                "INSERT INTO items (chat_id, item, bought) VALUES (%s, %s, FALSE)",
                [(chat_id, item.strip()) for item in items if item.strip()]
            )
        conn.commit()


def get_items(chat_id: int, only_pending=True) -> list[str]:
    with get_conn() as conn:
        with conn.cursor() as cur:
            if only_pending:
                cur.execute(
                    "SELECT item FROM items WHERE chat_id = %s AND bought = FALSE ORDER BY added_at",
                    (chat_id,)
                )
            else:
                cur.execute(
                    "SELECT item FROM items WHERE chat_id = %s ORDER BY added_at",
                    (chat_id,)
                )
            rows = cur.fetchall()
    return [row[0] for row in rows]


def mark_bought(chat_id: int, items_to_mark: list[str]) -> list[str]:
    """Marca items como comprados. Devuelve los pendientes restantes."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            for item in items_to_mark:
                cur.execute(
                    "UPDATE items SET bought = TRUE WHERE chat_id = %s AND LOWER(item) = LOWER(%s)",
                    (chat_id, item.strip())
                )
        conn.commit()
    return get_items(chat_id, only_pending=True)


def clear_bought(chat_id: int):
    """Elimina los items ya comprados."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM items WHERE chat_id = %s AND bought = TRUE", (chat_id,))
        conn.commit()


def clear_all(chat_id: int):
    """Elimina todos los items."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM items WHERE chat_id = %s", (chat_id,))
        conn.commit()
