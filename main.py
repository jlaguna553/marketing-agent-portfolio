"""
Punto de entrada del Agente de Marketing Automatizado.
Inicia FastAPI, sirve el frontend y registra todos los routers.
"""
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
import logging

from backend.database import init_db, AsyncSessionLocal
from backend.scheduler import start_scheduler, stop_scheduler
from backend.routers import chat, posts, webhook, leads, dev
from backend.routers.tickets import router as tickets_router, kb_router
from backend.config import get_settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)
settings = get_settings()

FRONTEND_DIR = Path(__file__).parent / "frontend"


async def _seed_knowledge_base():
    """Siembra la KB con información básica de Doña Felix si está vacía."""
    from sqlalchemy import select, func
    from backend.models import KnowledgeBase

    initial_entries = [
        ("¿Qué venden?", "Gorditas artesanales estilo Cortazar, Guanajuato: gorditas de queso y gorditas de migajas.", "menu"),
        ("¿Cuáles son los sabores disponibles?", "Tenemos gorditas de queso y gorditas de migajas, receta tradicional de Cortazar, Guanajuato.", "menu"),
        ("¿Cómo hago un pedido?", "Puedes hacer tu pedido aquí mismo por WhatsApp o Facebook. Dinos la cantidad y el sabor que deseas.", "pedidos"),
        ("¿Hacen pedidos para llevar?", "Sí, manejamos pedidos para llevar. Indícanos la cantidad y el horario en que pasarías.", "pedidos"),
        ("¿Hacen pedidos especiales o por mayoreo?", "Para pedidos especiales o por mayoreo, contáctanos directamente y con gusto te atendemos.", "pedidos"),
    ]

    if settings.kb_seed_file and Path(settings.kb_seed_file).exists():
        import json
        data = json.loads(Path(settings.kb_seed_file).read_text(encoding="utf-8"))
        initial_entries = [(d["question"], d["answer"], d.get("category", "general")) for d in data]

    async with AsyncSessionLocal() as db:
        count = (await db.execute(select(func.count()).select_from(KnowledgeBase))).scalar_one()
        if count == 0:
            for question, answer, category in initial_entries:
                db.add(KnowledgeBase(question=question, answer=answer, category=category))
            await db.commit()
            logger.info(f"KB inicial sembrada con {len(initial_entries)} entradas para {settings.business_name}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info(f"Iniciando Agente de Marketing para: {settings.business_name}")
    await init_db()
    await _seed_knowledge_base()
    start_scheduler()
    yield
    # Shutdown
    stop_scheduler()
    logger.info("Agente detenido.")


app = FastAPI(
    title="Marketing Agent API",
    description="Agente de marketing con IA para gestión de redes sociales",
    version="1.0.0",
    lifespan=lifespan
)

LOCAL_HOSTS = {"localhost", "127.0.0.1", "[::1]", "testserver"}


@app.middleware("http")
async def restrict_remote_admin(request, call_next):
    """Con un túnel (ngrok) el panel NO debe quedar público: desde fuera solo se permite el webhook de Meta."""
    if settings.restrict_remote_admin:
        host = request.headers.get("host", "").split(":")[0].lower()
        if host not in LOCAL_HOSTS and not request.url.path.startswith("/webhook/meta"):
            return JSONResponse({"detail": "No disponible desde fuera"}, status_code=404)
    return await call_next(request)


# Routers
app.include_router(chat.router)
app.include_router(posts.router)
app.include_router(webhook.router)
app.include_router(leads.router)
app.include_router(dev.router)
app.include_router(tickets_router)
app.include_router(kb_router)

# Endpoint de configuración del frontend
@app.get("/api/config")
async def get_config():
    return {
        "business_name": settings.business_name,
        "business_description": settings.business_description,
        "llm_provider": settings.llm_provider,
        "ollama_model": settings.ollama_content_model if settings.llm_provider == "ollama" else None,
        "facebook_configured": bool(settings.facebook_page_id),
        "instagram_configured": bool(settings.instagram_account_id),
        "whatsapp_configured": bool(settings.whatsapp_phone_number_id),
        "mock_mode": settings.mock_integrations,
        "booking_url": settings.booking_url,
    }


@app.get("/api/usage")
async def get_usage():
    """Ahorro de IA: respuestas gratis vs. llamadas al modelo, y tokens estimados evitados por RAG."""
    from backend import usage
    return usage.snapshot()


@app.get("/api/health/ollama")
async def check_ollama():
    """Verifica la conexión con Ollama y que el modelo esté disponible."""
    if settings.llm_provider != "ollama":
        return {"enabled": False, "message": "Proveedor activo: Anthropic"}
    from backend.ollama_client import check_ollama_connection
    ok, message = await check_ollama_connection()
    return {"enabled": True, "ok": ok, "message": message}

# Servir archivos estáticos del frontend
if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")

@app.get("/")
async def serve_index():
    return FileResponse(str(FRONTEND_DIR / "index.html"))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=settings.port,
        reload=True,
        log_level="info"
    )
