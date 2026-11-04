"""
Bandeja de salida para el modo local (MOCK_INTEGRATIONS=true).
En lugar de llamar a Meta/WhatsApp, guarda en memoria lo que se habría enviado.
(En memoria a propósito: evita bloqueos de SQLite y se limpia al reiniciar.)
"""
import itertools
from collections import deque
from datetime import datetime

_fake_ids = itertools.count(1)
_rows: deque = deque(maxlen=200)


def fake_id(prefix: str = "mock") -> str:
    return f"{prefix}.{next(_fake_ids)}"


async def record(channel: str, kind: str, content: str, recipient: str | None = None) -> None:
    _rows.appendleft({"id": next(_fake_ids), "channel": channel, "kind": kind, "recipient": recipient,
                      "content": content, "created_at": datetime.utcnow().isoformat()})


def latest(limit: int = 50) -> list[dict]:
    return list(_rows)[:limit]


def clear() -> None:
    _rows.clear()
