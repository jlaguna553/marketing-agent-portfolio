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

    # ── Modo local / pruebas ──────────────────────────────────
    # true = NO llama a Meta ni a WhatsApp: guarda lo que se enviaría en la "bandeja de salida" (/api/dev/outbox)
    # y, si no hay ANTHROPIC_API_KEY, usa una IA simulada. Ideal para probar el CRM sin credenciales.
    mock_integrations: bool = False
    database_url: str = "sqlite+aiosqlite:///./marketing_agent.db"

    # ── CRM y automatizaciones ────────────────────────────────
    owner_whatsapp: str = ""            # número del dueño para avisos (formato 52XXXXXXXXXX)
    notify_owner: bool = True           # avisar al dueño de leads nuevos y tickets
    followups_enabled: bool = True      # seguimiento automático a quien pidió agendar y no lo hizo
    followup_after_hours: float = 3.0   # horas sin avance antes de dar seguimiento
    followup_max: int = 2               # máximo de seguimientos por lead
    followup_check_seconds: int = 900   # cada cuánto revisa la automatización

    # ── Cloudflare Workers AI (cuota gratuita diaria de neuronas, compartida con tus Workers) ──
    # LLM_PROVIDER=workers_ai para usarlo. Token: dash.cloudflare.com → Mi perfil → Tokens de API → permiso "Workers AI".
    cf_account_id: str = ""
    cf_api_token: str = ""
    cf_response_model: str = "@cf/meta/llama-3.1-8b-instruct-fp8"  # ~3x más barato en neuronas que el 70B
    cf_content_model: str = "@cf/meta/llama-3.1-8b-instruct-fp8"
    cf_embedding_model: str = "@cf/baai/bge-m3"  # multilingüe; verifica su costo en la documentación de Cloudflare

    # ── Estudio de posts: Worker `felix-post-studio` (ver worker/studio/README) ──
    # Vacío + MOCK_INTEGRATIONS=true => texto simulado local. La clave es la misma que `wrangler secret put STUDIO_KEY`.
    studio_worker_url: str = ""
    studio_worker_key: str = ""
    studio_facts_k: int = 4             # entradas de la KB (RAG) que se mandan como datos verificados

    # ── RAG: enviar solo las entradas relevantes de la KB en cada prompt ──
    rag_enabled: bool = True
    rag_top_k: int = 4
    rag_min_entries: int = 6        # con menos entradas que esto se envía la KB completa
    rag_embeddings: bool = False    # true = búsqueda semántica con embeddings de Workers AI

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
    meta_app_secret: str = ""            # si se define, se valida la firma X-Hub-Signature-256 del webhook
    # Si true, el panel y la API solo responden desde localhost; desde fuera (p. ej. ngrok) solo /webhook/meta.
    restrict_remote_admin: bool = True
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
