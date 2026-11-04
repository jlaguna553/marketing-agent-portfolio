"""Contadores simples (en memoria) para ver cuánto se ahorra: respuestas gratis, llamadas al LLM y tokens estimados."""

_c = {"free_replies": 0, "llm_calls": 0, "est_prompt_tokens": 0, "est_tokens_saved_by_rag": 0, "limit_hits": 0}


def tokens(chars: int) -> int:
    return max(0, chars) // 4  # estimación rápida: ~4 caracteres por token


def free_reply() -> None:
    _c["free_replies"] += 1


def llm_call(prompt_chars: int, saved_chars: int = 0) -> None:
    _c["llm_calls"] += 1
    _c["est_prompt_tokens"] += tokens(prompt_chars)
    _c["est_tokens_saved_by_rag"] += tokens(saved_chars)


def limit_hit() -> None:
    _c["limit_hits"] += 1


def snapshot() -> dict:
    total = _c["free_replies"] + _c["llm_calls"]
    return {**_c, "free_reply_ratio": round(_c["free_replies"] / total, 2) if total else 0.0}


def reset() -> None:
    for k in _c:
        _c[k] = 0
