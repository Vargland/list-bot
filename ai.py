import os
import json
import tempfile
from pathlib import Path

from groq import Groq

_client = None


def get_client() -> Groq:
    global _client
    if _client is None:
        _client = Groq(api_key=os.environ["GROQ_API_KEY"])
    return _client


def transcribe_voice(ogg_bytes: bytes) -> str:
    """Transcribe un audio OGG (voz de Telegram) usando Whisper en Groq."""
    with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as f:
        f.write(ogg_bytes)
        tmp_path = f.name

    try:
        with open(tmp_path, "rb") as audio_file:
            result = get_client().audio.transcriptions.create(
                model="whisper-large-v3-turbo",
                file=audio_file,
                language="es"
            )
        return result.text
    finally:
        Path(tmp_path).unlink(missing_ok=True)


def extract_items(text: str) -> list[str]:
    """Extrae items de compra de un texto en lenguaje natural."""
    response = get_client().chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {
                "role": "system",
                "content": (
                    "Eres un asistente que extrae items de compra de mensajes en lenguaje natural en español. "
                    "Devuelve ÚNICAMENTE un JSON array con los items, sin explicaciones. "
                    "Ejemplo: [\"leche\", \"pan\", \"aceite\"]. "
                    "Si no hay items de compra, devuelve []. "
                    "Los items deben estar en singular y en minúscula."
                )
            },
            {"role": "user", "content": text}
        ],
        temperature=0,
        max_tokens=300
    )

    raw = response.choices[0].message.content.strip()
    try:
        items = json.loads(raw)
        return [str(i) for i in items if isinstance(i, str)]
    except json.JSONDecodeError:
        return []


def identify_bought_items(text: str, current_list: list[str]) -> list[str]:
    """Devuelve cuáles items de la lista fueron comprados según el mensaje."""
    if not current_list:
        return []

    lista_str = "\n".join(f"- {item}" for item in current_list)

    response = get_client().chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {
                "role": "system",
                "content": (
                    "Eres un asistente que interpreta qué items de una lista de compras ya fueron comprados. "
                    "Se te dará la lista actual y un mensaje del usuario. "
                    "Devuelve ÚNICAMENTE un JSON array con los items comprados (exactamente como aparecen en la lista). "
                    "Si el usuario dice que compró todo excepto algo, devuelve todo menos eso. "
                    "Ejemplo: [\"leche\", \"pan\"]. Si no hay ninguno, devuelve []."
                )
            },
            {
                "role": "user",
                "content": f"Lista actual:\n{lista_str}\n\nMensaje del usuario: {text}"
            }
        ],
        temperature=0,
        max_tokens=300
    )

    raw = response.choices[0].message.content.strip()
    try:
        items = json.loads(raw)
        return [str(i) for i in items if isinstance(i, str)]
    except json.JSONDecodeError:
        return []


def identify_item_to_delete(text: str, current_list: list[str]) -> str | None:
    """Identifica qué item quiere borrar el usuario. Devuelve el item exacto o None."""
    if not current_list:
        return None

    lista_str = "\n".join(f"- {item}" for item in current_list)

    response = get_client().chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {
                "role": "system",
                "content": (
                    "Eres un asistente que identifica qué item de una lista de compras quiere borrar el usuario. "
                    "Devuelve ÚNICAMENTE el nombre del item exactamente como aparece en la lista, sin explicaciones. "
                    "Si no podés identificarlo, devuelve null."
                )
            },
            {
                "role": "user",
                "content": f"Lista actual:\n{lista_str}\n\nMensaje del usuario: {text}"
            }
        ],
        temperature=0,
        max_tokens=50
    )

    raw = response.choices[0].message.content.strip()
    if raw.lower() == "null" or not raw:
        return None
    return raw


def identify_item_to_edit(text: str, current_list: list[str]) -> tuple[str, str] | None:
    """
    Identifica qué item quiere editar el usuario y por cuál reemplazarlo.
    Devuelve (item_viejo, item_nuevo) o None.
    """
    if not current_list:
        return None

    lista_str = "\n".join(f"- {item}" for item in current_list)

    response = get_client().chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {
                "role": "system",
                "content": (
                    "Eres un asistente que identifica qué item de una lista de compras quiere editar el usuario y por cuál reemplazarlo. "
                    "Devuelve ÚNICAMENTE un JSON con dos campos: {\"old\": \"item viejo\", \"new\": \"item nuevo\"}. "
                    "El campo 'old' debe ser exactamente como aparece en la lista. "
                    "Si no podés identificarlo, devuelve null."
                )
            },
            {
                "role": "user",
                "content": f"Lista actual:\n{lista_str}\n\nMensaje del usuario: {text}"
            }
        ],
        temperature=0,
        max_tokens=100
    )

    raw = response.choices[0].message.content.strip()
    if raw.lower() == "null" or not raw:
        return None
    try:
        data = json.loads(raw)
        return (data["old"], data["new"])
    except (json.JSONDecodeError, KeyError):
        return None
