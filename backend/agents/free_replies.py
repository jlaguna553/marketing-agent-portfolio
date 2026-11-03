"""
Capa de respuestas SIN costo de IA.

Antes de llamar al LLM, el agente intenta resolver el mensaje con:
  1. Saludos simples  -> bienvenida fija (+ enlace de agenda si existe)
  2. Intención de agendar/cotizar -> enlace de agenda
  3. Coincidencia con la Base de Conocimiento (similitud de palabras)
  4. Caché de respuestas anteriores a la misma pregunta

Solo si nada de eso aplica se llama al modelo. En un negocio con preguntas
repetitivas esto elimina la mayor parte de las llamadas.
"""
import re
import time
import unicodedata
from dataclasses import dataclass

from ..config import get_settings

settings = get_settings()

_STOPWORDS = {
    "a", "al", "algo", "como", "con", "cual", "cuales", "cuanto", "cuantos", "de", "del", "el",
    "en", "es", "esta", "estan", "hay", "la", "las", "lo", "los", "me", "mi", "mis", "no", "para",
    "por", "que", "se", "si", "su", "sus", "te", "tu", "tus", "un", "una", "y", "o", "u", "ya",
    "hola", "buenas", "buen", "dia", "dias", "tardes", "noches", "favor", "gracias", "quiero",
    "puedo", "pueden", "puedes", "saber", "tienen", "tiene", "manejan", "manejas", "hacen", "hace",
}
_GREETINGS = {"hola", "holaa", "buenas", "buenos", "dias", "tardes", "noches", "hey", "hi",
              "hello", "saludos", "que", "tal", "onda", "buen", "dia", "👋"}
_BOOKING_WORDS = {"agendar", "agenda", "cita", "asesoria", "asesorias", "llamada", "cotizar",
                  "cotizacion", "reunion", "consulta", "videollamada", "agendo"}


@dataclass
class FreeReply:
    text: str
    reason: str  # greeting | booking | kb | cache
    kb_id: int | None = None
    wants_booking: bool = False


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.lower())
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9ñ\s👋]", " ", text).strip()


def _stem(t: str) -> str:
    """Singular/plural básico: 'sistemas' == 'sistema', 'páginas' == 'pagina'."""
    return t[:-1] if len(t) > 4 and t.endswith("s") else t


def _tokens(text: str) -> set[str]:
    return {_stem(t) for t in normalize(text).split() if t and t not in _STOPWORDS}


def similarity(a: str, b: str) -> float:
    """Similitud 0-1 entre dos textos. Mezcla Jaccard y contención para tolerar frases cortas."""
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return 0.0
    inter = len(ta & tb)
    jaccard = inter / len(ta | tb)
    containment = inter / min(len(ta), len(tb))
    return max(jaccard, 0.85 * containment)


# ── Caché en memoria con TTL ──────────────────────────────────
_cache: dict[str, tuple[float, str]] = {}
_CACHE_MAX = 500


def cache_get(message: str) -> str | None:
    key = normalize(message)
    hit = _cache.get(key)
    if not hit:
        return None
    if time.time() - hit[0] > settings.reply_cache_ttl_seconds:
        _cache.pop(key, None)
        return None
    return hit[1]


def cache_put(message: str, reply: str) -> None:
    if len(_cache) >= _CACHE_MAX:
        _cache.pop(next(iter(_cache)))  # descarta la más antigua
    _cache[normalize(message)] = (time.time(), reply)


def is_greeting(message: str) -> bool:
    words = normalize(message).split()
    return 0 < len(words) <= 4 and all(w in _GREETINGS for w in words)


def wants_booking(message: str) -> bool:
    return bool(set(normalize(message).split()) & _BOOKING_WORDS)


def greeting_text() -> str:
    base = f"¡Hola! 👋 Soy el asistente de {settings.business_name}. ¿En qué te puedo ayudar?"
    if settings.booking_url:
        base += f"\n\nSi ya tienes una idea, agenda tu asesoría gratuita aquí: {settings.booking_url}"
    return base


def booking_text() -> str:
    if settings.booking_url:
        return (f"¡Con gusto! 📅 Agenda tu asesoría gratuita aquí y elige el horario que mejor te quede: "
                f"{settings.booking_url}\n\nSi quieres, cuéntame en una línea qué negocio tienes y qué te gustaría resolver.")
    return ("¡Con gusto! 📅 Cuéntame qué negocio tienes y qué te gustaría resolver, "
            "y te contactamos para agendar tu asesoría gratuita.")


def try_free_reply(message: str, kb_entries: list, has_history: bool) -> FreeReply | None:
    """Devuelve una respuesta sin LLM, o None si hay que consultar al modelo."""
    if not settings.free_replies_enabled:
        return None

    if is_greeting(message) and not has_history:
        return FreeReply(greeting_text(), "greeting")

    if wants_booking(message):
        return FreeReply(booking_text(), "booking", wants_booking=True)

    best, best_score = None, 0.0
    for e in kb_entries:
        score = similarity(message, e.question)
        if score > best_score:
            best, best_score = e, score
    if best is not None and best_score >= settings.kb_match_threshold:
        return FreeReply(best.answer, "kb", kb_id=best.id)

    if not has_history:
        cached = cache_get(message)
        if cached:
            return FreeReply(cached, "cache")
    return None
