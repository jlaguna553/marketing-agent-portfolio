"""
Cliente para Ollama local.
Llama al servidor Ollama (Windows) desde WSL2 usando su API REST.
Soporta streaming de texto y detección de acciones (publicar posts) via JSON en el output.

Configuración en Windows necesaria:
  1. Abrir PowerShell como Admin y ejecutar:
     setx OLLAMA_HOST "0.0.0.0" /M
  2. Reiniciar Ollama
  3. En .env poner OLLAMA_BASE_URL=http://localhost:11434
     (o la IP del host WSL2 si localhost no funciona)
"""
import json
import re
from typing import AsyncGenerator
import httpx
from .config import get_settings

settings = get_settings()


def _chat_url() -> str:
    return f"{settings.ollama_base_url}/api/chat"


def _build_messages(system: str, messages: list[dict]) -> list[dict]:
    """Construye la lista de mensajes con el system prompt al inicio."""
    result = [{"role": "system", "content": system}]
    for m in messages:
        result.append({"role": m["role"], "content": m["content"]})
    return result


async def stream_chat(
    system: str,
    messages: list[dict],
    model: str,
) -> AsyncGenerator[str, None]:
    """
    Hace streaming de texto desde Ollama.
    Yield: chunks de texto tal como los devuelve el modelo.
    """
    payload = {
        "model": model,
        "messages": _build_messages(system, messages),
        "stream": True,
        "options": {
            "temperature": 0.7,
            "num_predict": 2048,
        }
    }

    async with httpx.AsyncClient(timeout=120) as client:
        async with client.stream("POST", _chat_url(), json=payload) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    chunk = data.get("message", {}).get("content", "")
                    if chunk:
                        yield chunk
                    if data.get("done"):
                        break
                except json.JSONDecodeError:
                    continue


async def complete(
    system: str,
    messages: list[dict],
    model: str,
) -> str:
    """Completado simple (no streaming) desde Ollama."""
    payload = {
        "model": model,
        "messages": _build_messages(system, messages),
        "stream": False,
        "options": {"temperature": 0.7, "num_predict": 1024}
    }
    async with httpx.AsyncClient(timeout=120) as client:
        response = await client.post(_chat_url(), json=payload)
        response.raise_for_status()
        data = response.json()
        return data.get("message", {}).get("content", "")


def extract_action_from_text(text: str) -> dict | None:
    """
    Busca en el texto un bloque JSON con la acción de publicar un post.
    Ollama no tiene tool calling nativo en todos los modelos,
    así que detectamos la acción via el JSON que el modelo incluye en su respuesta.
    """
    # Buscar bloques ```json ... ```
    pattern = r"```json\s*([\s\S]*?)```"
    matches = re.findall(pattern, text)
    for match in matches:
        try:
            data = json.loads(match.strip())
            # Si tiene post_content, es la acción de crear post
            if "post_content" in data:
                return data
        except json.JSONDecodeError:
            continue
    return None


async def check_ollama_connection() -> tuple[bool, str]:
    """Verifica que Ollama esté disponible y el modelo configurado exista."""
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(f"{settings.ollama_base_url}/api/tags")
            resp.raise_for_status()
            models = [m["name"].split(":")[0] for m in resp.json().get("models", [])]
            content_model_base = settings.ollama_content_model.split(":")[0]
            if content_model_base not in models:
                available = ", ".join(models) if models else "ninguno"
                return False, (
                    f"Modelo '{settings.ollama_content_model}' no encontrado. "
                    f"Modelos disponibles: {available}. "
                    f"Ejecuta: ollama pull {settings.ollama_content_model}"
                )
            return True, f"Ollama OK — modelo: {settings.ollama_content_model}"
    except httpx.ConnectError:
        return False, (
            f"No se puede conectar a Ollama en {settings.ollama_base_url}. "
            "Verifica que Ollama esté corriendo en Windows y que OLLAMA_HOST=0.0.0.0"
        )
    except Exception as e:
        return False, f"Error al conectar con Ollama: {e}"
