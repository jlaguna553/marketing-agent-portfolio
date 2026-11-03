from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # ── Proveedor de IA ───────────────────────────────────────
    # "anthropic" usa Claude API | "ollama" usa tu servidor local
    llm_provider: str = "anthropic"

    # Claude API (solo necesario si llm_provider=anthropic)
    anthropic_api_key: str = ""
    # Modelos configurables. Por defecto el más económico para ambas tareas;
    # sube el de contenido solo si necesitas más calidad de redacción.
    anthropic_content_model: str = "claude-haiku-5-5"
    anthropic_response_model: str = "claude-haiku-5-5"

    # ── Control de costos ─────────────────────────────────────
    # Responder SIN llamar al LLM cuando la KB o una regla ya cubre la pregunta.
    free_replies_enabled: bool = True
    kb_match_threshold: float = 0.6     # 0-1; similitud mínima para responder directo desde la KB
    reply_cache_ttl_seconds: int = 86400  # reutiliza respuestas a preguntas idénticas
    max_history_messages: int = 4       # mensajes previos enviados al LLM
    max_reply_tokens: int = 350

    # Ollama (solo necesario si llm_provider=ollama)
    # Desde WSL2 hacia Windows usa http://localhost:11434
    # Si no funciona, usa la IP del host: cat /etc/resolv.conf | grep nameserver
    ollama_base_url: str = "http://localhost:11434"
    ollama_content_model: str = "llama3.2"   # Modelo para generar posts
    ollama_response_model: str = "llama3.2"  # Modelo para responder clientes

    # ── Meta / Redes Sociales ─────────────────────────────────
    meta_access_token: str = ""
    facebook_page_id: str = ""
    instagram_account_id: str = ""
    meta_webhook_verify_token: str = "verify_token"
    whatsapp_phone_number_id: str = ""
    whatsapp_access_token: str = ""
    app_base_url: str = "http://localhost:8000"
    port: int = 8000

    # ── Negocio ───────────────────────────────────────────────
    business_name: str = "Mi Negocio"
    business_description: str = "Un negocio dedicado a ofrecer productos y servicios de calidad"
    # Rol del asistente en el prompt, ej. "una gordería artesanal" o "una empresa de desarrollo de software"
    # Archivo JSON con la KB inicial (lista de {question, answer, category}). Vacío = KB integrada.
    kb_seed_file: str = ""
    business_role: str = "un negocio local"
    # Enlace de agenda (Cal.com, Google Calendar, etc.) que el bot comparte al detectar interés
    booking_url: str = ""
    default_language: str = "es"
    timezone: str = "America/Mexico_City"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache
def get_settings() -> Settings:
    return Settings()
