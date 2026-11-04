"""
Recuperación (RAG) sobre la base de conocimiento: en lugar de meter TODA la KB en cada prompt,
se envían solo las K entradas más relevantes. Menos tokens por llamada, y la KB puede crecer sin encarecer.

Dos modos, sin infraestructura extra:
  1. Léxico (por defecto, $0): coincidencia de palabras entre la pregunta y cada entrada.
  2. Híbrido con embeddings (RAG_EMBEDDINGS=true): vectores de Workers AI guardados en la propia base
     (SQLite) y similitud coseno en Python. Para cientos de entradas es instantáneo; una base vectorial
     dedicada (Vectorize, pgvector) solo se justifica con miles de vectores.
"""
import hashlib
import json
import logging
import math

from sqlalchemy.ext.asyncio import AsyncSession

from . import workers_ai
from .agents.free_replies import _tokens
from .config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


def entry_text(e) -> str:
    return f"{e.question}\n{e.answer}"


def _hash(e) -> str:
    return hashlib.sha1(entry_text(e).encode()).hexdigest()


def lexical_score(query: str, e) -> float:
    q = _tokens(query)
    if not q:
        return 0.0
    return len(q & _tokens(entry_text(e))) / len(q)


def cosine(a: list[float], b: list[float]) -> float:
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    return sum(x * y for x, y in zip(a, b)) / (na * nb) if na and nb else 0.0


async def ensure_embeddings(db: AsyncSession, entries: list) -> int:
    """Calcula (en lote) los vectores que faltan o quedaron viejos porque la entrada cambió."""
    stale = [e for e in entries if not e.embedding or e.embedding_hash != _hash(e)]
    if not stale:
        return 0
    vectors = await workers_ai.embed([entry_text(e) for e in stale])
    for e, v in zip(stale, vectors):
        e.embedding = json.dumps(v)
        e.embedding_hash = _hash(e)
    await db.commit()
    return len(stale)


async def retrieve(db: AsyncSession, query: str, entries: list, k: int | None = None) -> list:
    k = k or settings.rag_top_k
    scores = {e.id: lexical_score(query, e) for e in entries}

    if settings.rag_embeddings:
        try:
            await ensure_embeddings(db, entries)
            qv = (await workers_ai.embed([query]))[0]
            for e in entries:
                scores[e.id] = 0.7 * cosine(qv, json.loads(e.embedding)) + 0.3 * scores[e.id]
        except workers_ai.WorkersAIError as err:
            logger.warning("RAG: embeddings no disponibles (%s); uso coincidencia léxica", err)

    ranked = sorted(entries, key=lambda e: (scores[e.id], e.times_used or 0), reverse=True)
    return ranked[:k]
