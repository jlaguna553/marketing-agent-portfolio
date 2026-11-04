"""
Agente de generación de contenido de marketing.
Soporta dos proveedores: Anthropic (Claude) y Ollama (modelos locales).
Genera posts, captions, hashtags y responde preguntas del dueño del negocio.
"""
import json
from typing import AsyncGenerator
from ..config import get_settings

settings = get_settings()

# ── System prompt compartido por ambos proveedores ────────────
SYSTEM_PROMPT = f"""Eres un experto en marketing digital y community manager para el negocio "{settings.business_name}".

Descripción del negocio: {settings.business_description}
Idioma principal: {settings.default_language}

Tu trabajo es ayudar al dueño del negocio a:
1. Crear posts atractivos para Facebook e Instagram
2. Generar contenido publicitario persuasivo
3. Sugerir hashtags relevantes
4. Programar y planificar campañas de marketing
5. Responder sus preguntas sobre estrategia de marketing

Cuando el dueño pida un post, SIEMPRE incluye este bloque JSON exacto en tu respuesta:
```json
{{
  "post_content": "Texto del post aquí...",
  "hashtags": ["#hashtag1", "#hashtag2"],
  "platform": "facebook|instagram|all",
  "image_suggestion": "Descripción de imagen sugerida o null",
  "best_time": "Mejor hora para publicar o null",
  "publish_now": false,
  "scheduled_time": null
}}
```

Si el dueño pide publicar inmediatamente, pon "publish_now": true.
Si el dueño pide programar, pon "publish_now": false y la hora ISO en "scheduled_time".

Después del JSON puedes agregar explicaciones adicionales.

Reglas:
- Escribe en {settings.default_language}
- Usa emojis apropiados
- Posts de Facebook: más largos y narrativos
- Posts de Instagram: visuales, 15-20 hashtags
- Tono: profesional pero cercano
"""

# ── Tool definition (solo Anthropic la usa nativamente) ───────
_ANTHROPIC_TOOLS = [
    {
        "name": "create_post",
        "description": "Crea y opcionalmente programa un post para redes sociales",
        "input_schema": {
            "type": "object",
            "properties": {
                "content": {"type": "string", "description": "Texto completo del post"},
                "platform": {
                    "type": "string",
                    "enum": ["facebook", "instagram", "all"],
                    "description": "Plataforma donde publicar"
                },
                "hashtags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Lista de hashtags"
                },
                "publish_now": {"type": "boolean", "description": "Si es true, publica inmediatamente"},
                "scheduled_time": {
                    "type": "string",
                    "description": "ISO datetime para publicación programada"
                }
            },
            "required": ["content", "platform", "publish_now"]
        }
    }
]


# ──────────────────────────────────────────────────────────────
#  Proveedor: Anthropic
# ──────────────────────────────────────────────────────────────
async def _anthropic_stream(
    messages: list[dict],
    tool_callback=None
) -> AsyncGenerator[str, None]:
    import anthropic
    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

    api_messages = [{"role": m["role"], "content": m["content"]} for m in messages]

    async with client.messages.stream(
        model=settings.anthropic_content_model,
        max_tokens=2048,
        system=[{"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}],
        tools=_ANTHROPIC_TOOLS,
        messages=api_messages,
    ) as stream:
        tool_use_block = None
        async for event in stream:
            if event.type == "content_block_start":
                if hasattr(event.content_block, "type") and event.content_block.type == "tool_use":
                    tool_use_block = {
                        "id": event.content_block.id,
                        "name": event.content_block.name,
                        "input_json": ""
                    }
            elif event.type == "content_block_delta":
                if hasattr(event.delta, "text"):
                    yield event.delta.text
                elif hasattr(event.delta, "partial_json") and tool_use_block:
                    tool_use_block["input_json"] += event.delta.partial_json
            elif event.type == "content_block_stop":
                if tool_use_block and tool_callback:
                    try:
                        tool_input = json.loads(tool_use_block["input_json"])
                        await tool_callback(tool_use_block["name"], tool_input)
                    except json.JSONDecodeError:
                        pass
                    tool_use_block = None
            elif event.type == "message_stop":
                break


async def _anthropic_complete(prompt: str) -> str:
    import anthropic
    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    response = await client.messages.create(
        model=settings.anthropic_content_model,
        max_tokens=1024,
        system=[{"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": prompt}]
    )
    return response.content[0].text


# ──────────────────────────────────────────────────────────────
#  Proveedor: Ollama
# ──────────────────────────────────────────────────────────────
async def _ollama_stream(
    messages: list[dict],
    tool_callback=None
) -> AsyncGenerator[str, None]:
    from ..ollama_client import stream_chat, extract_action_from_text

    accumulated = ""
    action_dispatched = False

    async for chunk in stream_chat(
        system=SYSTEM_PROMPT,
        messages=messages,
        model=settings.ollama_content_model,
    ):
        accumulated += chunk
        yield chunk

    # Con Ollama, la "tool call" se detecta del JSON al final del stream
    if tool_callback and not action_dispatched:
        from ..ollama_client import extract_action_from_text
        action = extract_action_from_text(accumulated)
        if action and action.get("post_content"):
            tool_input = {
                "content": action.get("post_content", ""),
                "platform": action.get("platform", "all"),
                "hashtags": action.get("hashtags", []),
                "publish_now": action.get("publish_now", False),
                "scheduled_time": action.get("scheduled_time"),
            }
            await tool_callback("create_post", tool_input)


async def _ollama_complete(prompt: str) -> str:
    from ..ollama_client import complete
    return await complete(
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
        model=settings.ollama_content_model,
    )


# ──────────────────────────────────────────────────────────────
#  API pública — el router solo llama estas dos funciones
# ──────────────────────────────────────────────────────────────
async def _workers_ai_stream(messages: list[dict], tool_callback=None) -> AsyncGenerator[str, None]:
    """Workers AI por REST (sin streaming): devuelve el texto completo y detecta el JSON del post al final."""
    from .. import workers_ai
    from ..ollama_client import extract_action_from_text
    try:
        text = await workers_ai.complete(SYSTEM_PROMPT, messages, settings.cf_content_model, 1024)
    except workers_ai.WorkersAIError as e:
        yield f"⚠️ No pude generar el contenido ahora: {e}"
        return
    yield text
    action = extract_action_from_text(text)
    if tool_callback and action and action.get("post_content"):
        await tool_callback("create_post", {
            "content": action.get("post_content", ""), "platform": action.get("platform", "all"),
            "hashtags": action.get("hashtags", []), "publish_now": action.get("publish_now", False),
            "scheduled_time": action.get("scheduled_time"),
        })


async def chat_stream(
    messages: list[dict],
    tool_callback=None
) -> AsyncGenerator[str, None]:
    """Streaming del agente hacia el chat del dueño. Enruta según LLM_PROVIDER."""
    if settings.llm_provider == "workers_ai":
        async for chunk in _workers_ai_stream(messages, tool_callback):
            yield chunk
    elif settings.llm_provider == "ollama":
        async for chunk in _ollama_stream(messages, tool_callback):
            yield chunk
    else:
        async for chunk in _anthropic_stream(messages, tool_callback):
            yield chunk


async def generate_post_simple(prompt: str) -> dict:
    """Genera un post sin streaming. Útil para uso interno."""
    if settings.llm_provider == "workers_ai":
        from .. import workers_ai
        text = await workers_ai.complete(SYSTEM_PROMPT, [{"role": "user", "content": prompt}], settings.cf_content_model, 1024)
    elif settings.llm_provider == "ollama":
        text = await _ollama_complete(prompt)
    else:
        text = await _anthropic_complete(prompt)

    result = {
        "post_content": text,
        "hashtags": [],
        "platform": "all",
        "image_suggestion": None,
        "best_time": None,
        "scheduled": False
    }
    try:
        import re
        match = re.search(r"```json\s*([\s\S]*?)```", text)
        if match:
            parsed = json.loads(match.group(1).strip())
            result.update(parsed)
    except Exception:
        pass
    return result
