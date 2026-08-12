from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # ── Proveedor de IA ───────────────────────────────────────
    # "anthropic" usa Claude API | "ollama" usa tu servidor local
    llm_provider: str = "anthropic"

    # Claude API (solo necesario si llm_provider=anthropic)
    anthropic_api_key: str = ""

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
    default_language: str = "es"
    timezone: str = "America/Mexico_City"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache
def get_settings() -> Settings:
    return Settings()
