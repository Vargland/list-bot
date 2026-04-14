import os
import asyncio
import logging
from dotenv import load_dotenv

from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)

import db
import ai

load_dotenv()

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

ASKING_NAME = 1

KEYWORDS_LIST_NAMES = ["dame la lista con nombres", "lista con nombres", "mostrar lista con nombres"]
KEYWORDS_LIST = ["dame la lista", "la lista", "qué tengo", "que tengo", "mostrar lista"]
KEYWORDS_TOTAL = ["compré todo", "compre todo", "ya compré todo", "compra total", "limpiar lista", "borrar lista", "lista nueva"]
KEYWORDS_PARTIAL = ["compré", "compre", "compra parcial", "ya compré", "ya compre"]
KEYWORDS_DELETE = ["borrá", "borra", "elimina", "eliminá", "sacá", "saca", "quita", "quitá", "remove", "delete"]
KEYWORDS_EDIT = ["cambiá", "cambia", "reemplazá", "reemplaza", "editá", "edita", "renombrá", "renombra"]


def _format_list(items: list[dict], show_names=False) -> str:
    if not items:
        return "La lista está vacía."
    if show_names:
        lines = "\n".join(f"  {i+1}. {row['item']} — {row['name']}" for i, row in enumerate(items))
    else:
        lines = "\n".join(f"  {i+1}. {row['item']}" for i, row in enumerate(items))
    return f"Lista de compras ({len(items)} items):\n\n{lines}"


def _detect_intent(text: str) -> str | None:
    lower = text.lower()
    for kw in KEYWORDS_LIST_NAMES:
        if kw in lower:
            return "list_names"
    for kw in KEYWORDS_LIST:
        if kw in lower:
            return "list"
    for kw in KEYWORDS_TOTAL:
        if kw in lower:
            return "total"
    if "parcial" in lower:
        return "partial"
    for kw in KEYWORDS_PARTIAL:
        if kw in lower:
            return "partial"
    for kw in KEYWORDS_EDIT:
        if kw in lower:
            return "edit"
    for kw in KEYWORDS_DELETE:
        if kw in lower:
            return "delete"
    return None


async def _ensure_registered(update: Update) -> str | None:
    """Devuelve el nombre del usuario si está registrado, sino None."""
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    return await db.get_user_name(user_id, chat_id)


# --- Registro de nombre ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    name = await db.get_user_name(user_id, chat_id)

    if name:
        await update.message.reply_text(
            f"Hola {name}! Ya estás registrado.\n\n"
            "Mandame notas de voz o texto con lo que necesitás comprar."
        )
        return ConversationHandler.END

    await update.message.reply_text(
        "Hola! Soy el bot de lista de compras.\n\n"
        "¿Cómo te llamás? (así sé quién agrega cada cosa a la lista)"
    )
    return ASKING_NAME


async def receive_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.message.text.strip()
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id

    await db.register_user(user_id, chat_id, name)
    await update.message.reply_text(
        f"Listo, {name}! Ya podés empezar.\n\n"
        "Mandame notas de voz o texto con lo que necesitás comprar.\n"
        "Decime \"dame la lista\" para ver todo.\n"
        "Decime \"compré todo\" o \"compré el pan\" cuando hagas las compras."
    )
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Cancelado.")
    return ConversationHandler.END


# --- Lógica principal ---

async def _process_text(chat_id: int, user_id: int, text: str, update: Update):
    intent = _detect_intent(text)

    if intent == "list_names":
        items = await db.get_items(chat_id)
        await update.message.reply_text(_format_list(items, show_names=True))
        return

    if intent == "list":
        items = await db.get_items(chat_id)
        await update.message.reply_text(_format_list(items))
        return

    if intent == "total":
        current = await db.get_items(chat_id)
        await db.mark_bought(chat_id, [r["item"] for r in current])
        await update.message.reply_text("Compra total registrada. Lista nueva lista cuando quieras!")
        return

    if intent == "partial":
        current = await db.get_items(chat_id)
        if not current:
            await update.message.reply_text("La lista ya está vacía.")
            return

        await update.message.reply_text("Identificando qué compraste...")
        bought = ai.identify_bought_items(text, [r["item"] for r in current])

        if not bought:
            await update.message.reply_text(
                "No pude identificar qué compraste. Podés decirme algo como:\n"
                "\"Compré la leche, el pan y el aceite\""
            )
            return

        remaining = await db.mark_bought(chat_id, bought)
        bought_str = ", ".join(bought)
        msg = f"Listo! Marqué como comprado: {bought_str}\n\n{_format_list(remaining)}"
        await update.message.reply_text(msg)
        return

    if intent == "delete":
        current = await db.get_items(chat_id)
        if not current:
            await update.message.reply_text("La lista ya está vacía.")
            return

        item_to_delete = ai.identify_item_to_delete(text, [r["item"] for r in current])
        if not item_to_delete:
            await update.message.reply_text(
                "No pude identificar qué querés borrar. Decime algo como:\n"
                "\"Borrá la leche\""
            )
            return

        deleted = await db.delete_item(chat_id, item_to_delete)
        if deleted:
            remaining = await db.get_items(chat_id)
            await update.message.reply_text(f"Borré: {item_to_delete}\n\n{_format_list(remaining)}")
        else:
            await update.message.reply_text(f"No encontré \"{item_to_delete}\" en la lista.")
        return

    if intent == "edit":
        current = await db.get_items(chat_id)
        if not current:
            await update.message.reply_text("La lista ya está vacía.")
            return

        result = ai.identify_item_to_edit(text, [r["item"] for r in current])
        if not result:
            await update.message.reply_text(
                "No pude identificar qué querés editar. Decime algo como:\n"
                "\"Cambiá la leche por leche descremada\""
            )
            return

        old_name, new_name = result
        edited = await db.edit_item(chat_id, old_name, new_name)
        if edited:
            remaining = await db.get_items(chat_id)
            await update.message.reply_text(f"Cambié \"{old_name}\" por \"{new_name}\"\n\n{_format_list(remaining)}")
        else:
            await update.message.reply_text(f"No encontré \"{old_name}\" en la lista.")
        return

    # Sin intent → extraer items
    items = ai.extract_items(text)
    if items:
        await db.add_items(chat_id, user_id, items)
        items_str = ", ".join(items)
        await update.message.reply_text(f"Agregué: {items_str}")
    else:
        await update.message.reply_text(
            "No encontré items de compra en tu mensaje.\n"
            "Podés decirme \"dame la lista\" para ver lo que tenés."
        )


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id

    name = await db.get_user_name(user_id, chat_id)
    if not name:
        await update.message.reply_text(
            "Primero necesito saber tu nombre. Mandame /start para registrarte."
        )
        return

    await _process_text(chat_id, user_id, update.message.text, update)


async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id

    name = await db.get_user_name(user_id, chat_id)
    if not name:
        await update.message.reply_text(
            "Primero necesito saber tu nombre. Mandame /start para registrarte."
        )
        return

    await update.message.reply_text("Escuchando tu nota de voz...")
    voice = update.message.voice
    file = await context.bot.get_file(voice.file_id)
    ogg_bytes = bytes(await file.download_as_bytearray())

    text = ai.transcribe_voice(ogg_bytes)
    logger.info(f"Transcripción ({name}): {text}")

    await update.message.reply_text(f'Escuché: "{text}"')
    await _process_text(chat_id, user_id, text, update)


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.error("Exception:", exc_info=context.error)

    if isinstance(update, Update) and update.effective_message:
        error = context.error
        if "insufficient_quota" in str(error) or "429" in str(error):
            msg = "Límite de Groq alcanzado. Esperá un momento e intentá de nuevo."
        elif "401" in str(error) or "invalid_api_key" in str(error):
            msg = "API key de Groq inválida. Revisá el .env."
        elif "NetworkError" in type(error).__name__ or "TimedOut" in type(error).__name__:
            msg = "Error de red. Intentá de nuevo."
        else:
            msg = f"Ocurrió un error: {type(error).__name__}"

        await update.effective_message.reply_text(f"⚠️ {msg}")


async def post_init(app):
    await db.init_db()


def main():
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    app = ApplicationBuilder().token(token).post_init(post_init).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            ASKING_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_name)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    app.add_handler(conv_handler)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    app.add_error_handler(error_handler)

    logger.info("Bot iniciado.")
    app.run_polling()


if __name__ == "__main__":
    asyncio.set_event_loop(asyncio.new_event_loop())
    main()
