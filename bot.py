import os
import asyncio
import logging
from dotenv import load_dotenv

from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
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

# Palabras clave para detectar intenciones
KEYWORDS_LIST = ["dame la lista", "la lista", "qué tengo", "que tengo", "mostrar lista"]
KEYWORDS_TOTAL = ["compré todo", "compre todo", "ya compré todo", "compra total", "limpiar lista", "borrar lista", "lista nueva"]
KEYWORDS_PARTIAL = ["compré", "compre", "compra parcial", "ya compré", "ya compre"]


def _format_list(items: list[str]) -> str:
    if not items:
        return "La lista está vacía."
    lines = "\n".join(f"  {i+1}. {item}" for i, item in enumerate(items))
    return f"Lista de compras ({len(items)} items):\n\n{lines}"


def _detect_intent(text: str) -> str | None:
    lower = text.lower()
    for kw in KEYWORDS_LIST:
        if kw in lower:
            return "list"
    for kw in KEYWORDS_TOTAL:
        if kw in lower:
            return "total"
    # "parcial" antes que "compré" para que no haga match con el parcial en total
    if "parcial" in lower:
        return "partial"
    for kw in KEYWORDS_PARTIAL:
        if kw in lower:
            return "partial"
    return None


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.effective_user.first_name or "ahí"
    await update.message.reply_text(
        f"Hola {name}! Soy tu bot de lista de compras.\n\n"
        "Podés:\n"
        "  Mandarme notas de voz o texto con lo que necesitás comprar.\n"
        "  Decirme \"dame la lista\" para ver todo.\n"
        "  Decirme \"compré todo\" para limpiar la lista.\n"
        "  Decirme \"compré el pan y la leche\" para marcar como comprado parcialmente.\n\n"
        "Empezá a agregar cosas cuando quieras!"
    )


async def _process_text(chat_id: int, text: str, update: Update):
    intent = _detect_intent(text)

    if intent == "list":
        items = db.get_items(chat_id)
        await update.message.reply_text(_format_list(items))
        return

    if intent == "total":
        db.mark_bought(chat_id, db.get_items(chat_id))
        db.clear_bought(chat_id)
        await update.message.reply_text("Compra total registrada. Lista limpiada, empezamos de cero!")
        return

    if intent == "partial":
        current = db.get_items(chat_id)
        if not current:
            await update.message.reply_text("La lista ya está vacía.")
            return

        await update.message.reply_text("Identificando qué compraste...")
        bought = ai.identify_bought_items(text, current)

        if not bought:
            await update.message.reply_text(
                "No pude identificar qué compraste. Podés decirme algo como:\n"
                "\"Compré la leche, el pan y el aceite\""
            )
            return

        remaining = db.mark_bought(chat_id, bought)
        bought_str = ", ".join(bought)
        msg = f"Listo! Marqué como comprado: {bought_str}\n\n{_format_list(remaining)}"
        await update.message.reply_text(msg)
        return

    # Sin intent detectado → intentar extraer items de compra
    items = ai.extract_items(text)
    if items:
        db.add_items(chat_id, items)
        items_str = ", ".join(items)
        await update.message.reply_text(f"Agregué: {items_str}")
    else:
        await update.message.reply_text(
            "No encontré items de compra en tu mensaje.\n"
            "Podés decirme \"dame la lista\" para ver lo que tenés."
        )


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _process_text(update.effective_chat.id, update.message.text, update)


async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    await update.message.reply_text("Escuchando tu nota de voz...")

    voice = update.message.voice
    file = await context.bot.get_file(voice.file_id)
    ogg_bytes = bytes(await file.download_as_bytearray())

    text = ai.transcribe_voice(ogg_bytes)
    logger.info(f"Transcripción: {text}")

    await update.message.reply_text(f'Escuché: "{text}"')

    await _process_text(chat_id, text, update)


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


def main():
    db.init_db()

    token = os.environ["TELEGRAM_BOT_TOKEN"]
    app = ApplicationBuilder().token(token).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    app.add_error_handler(error_handler)

    logger.info("Bot iniciado.")
    app.run_polling()


if __name__ == "__main__":
    # Python 3.14 fix: asyncio no crea el event loop automáticamente
    asyncio.set_event_loop(asyncio.new_event_loop())
    main()
