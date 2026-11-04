"""
Cliente de Cloudflare Workers AI por REST (modelos abiertos con cuota gratuita diaria).

Uso desde el agente (Python): no necesita un Worker intermedio.
  POST https://api.cloudflare.com/client/v4/accounts/{ACCOUNT_ID}/ai/run/{MODELO}

La cuota gratuita es de 10,000 neuronas por día para toda la cuenta (se comparte con tus Workers,
por ejemplo cv-online). Al agotarse, Cloudflare responde error 3036 / HTTP 429: aquí se traduce a
DailyLimitReached para que el agente degrade con elegancia (ticket para una persona) en lugar de fallar.
"""
import logging

import httpx

from .config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

API_BASE = "https://api.cloudflare.com/client/v4/accounts"


class WorkersAIError(Exception):
    pass


class DailyLimitReached(WorkersAIError):
    """Se agotó la cuota diaria gratuita de neuronas."""


async def _run(model: str, payload: dict) -> dict:
    if not (settings.cf_account_id and settings.cf_api_token):
        raise WorkersAIError("Faltan CF_ACCOUNT_ID y/o CF_API_TOKEN")
    url = f"{API_BASE}/{settings.cf_account_id}/ai/run/{model}"
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(url, json=payload, headers={"Authorization": f"Bearer {settings.cf_api_token}"})
    try:
        data = resp.json()
    except ValueError:
        data = {}
    errors = data.get("errors") or []
    if resp.status_code == 429 or any(e.get("code") == 3036 for e in errors):
        raise DailyLimitReached("Cuota diaria gratuita de Workers AI agotada")
    if not resp.is_success or data.get("success") is False:
        raise WorkersAIError(f"Workers AI {resp.status_code}: {errors or resp.text[:200]}")
    return data.get("result") or {}


async def complete(system: str, messages: list[dict], model: str, max_tokens: int = 350) -> str:
    payload = {
        "messages": [{"role": "system", "content": system}] + [{"role": m["role"], "content": m["content"]} for m in messages],
        "max_tokens": max_tokens,
        "temperature": 0.3,
    }
    result = await _run(model, payload)
    if isinstance(result.get("response"), str):
        return result["response"]
    choices = result.get("choices")
    if choices:
        return choices[0].get("message", {}).get("content", "")
    raise WorkersAIError("Respuesta de Workers AI sin texto")


async def embed(texts: list[str], model: str | None = None) -> list[list[float]]:
    result = await _run(model or settings.cf_embedding_model, {"text": texts})
    vectors = result.get("data")
    if not vectors or len(vectors) != len(texts):
        raise WorkersAIError("Respuesta de embeddings inválida")
    return vectors
