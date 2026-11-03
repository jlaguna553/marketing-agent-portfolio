"""
Estudio de posts: pegas imágenes + describes la campaña -> texto (Worker de Cloudflare) + plantilla de marca.
Las imágenes no se analizan; solo se ponen en el post.
"""
from datetime import datetime

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .. import rag, studio
from ..config import get_settings
from ..database import get_db
from ..models import KnowledgeBase, Post

router = APIRouter(prefix="/api/studio", tags=["studio"])
settings = get_settings()

NETWORKS = {"facebook", "instagram", "both"}
TONES = {"cercano", "profesional", "divertido"}


def _http(e: studio.StudioError) -> HTTPException:
    status = {"daily_limit": 429, "rate_limited": 429, "not_configured": 503, "unauthorized": 502,
              "unreachable": 502, "worker_error": 502}.get(e.code, 400)
    return HTTPException(status_code=status, detail={"code": e.code, "message": str(e)})


@router.get("/status")
async def status():
    return {
        "worker_configured": bool(settings.studio_worker_url),
        "simulated": not settings.studio_worker_url and settings.mock_integrations,
    }


@router.post("/generate")
async def generate(
    campaign: str = Form(..., min_length=10, max_length=2000),
    network: str = Form("both"),
    tone: str = Form("cercano"),
    cta: str = Form("", max_length=120),
    images: list[UploadFile] = File(default=[]),
    db: AsyncSession = Depends(get_db),
):
    if network not in NETWORKS or tone not in TONES:
        raise HTTPException(400, detail={"code": "bad_request", "message": "network o tono inválido"})
    if len(images) > studio.MAX_IMAGES:
        raise HTTPException(400, detail={"code": "too_many_images", "message": f"Máximo {studio.MAX_IMAGES} imágenes"})

    # Valida las imágenes ANTES de gastar cuota del modelo.
    prepared = []
    try:
        for f in images:
            prepared.append(studio.sanitize_image(await f.read(studio.MAX_IMAGE_BYTES + 1)))
    except studio.StudioError as e:
        raise _http(e)

    # RAG: solo los datos más relevantes de la KB viajan al Worker (precios, servicios reales).
    entries = (await db.execute(select(KnowledgeBase))).scalars().all()
    top = await rag.retrieve(db, campaign, entries, k=settings.studio_facts_k) if entries else []
    facts = [f"{e.question} {e.answer}" for e in top]

    try:
        result = await studio.generate_copy(campaign, network, tone, cta.strip(), facts)
    except studio.StudioError as e:
        raise _http(e)

    post_id = studio.new_id()
    sources = [f"media/studio/src/{studio.save_source(img, post_id, i).name}" for i, img in enumerate(prepared)]
    post = result["post"]
    studio.compose_template(studio.source_path(post_id), post["headline"], post["cta"], studio.composed_path(post_id))
    return {
        "id": post_id,
        "post": post,
        "warnings": result["warnings"],
        "source": result["source"],
        "facts_used": facts,
        "image_url": f"media/studio/{post_id}.png",
        "extra_images_saved": max(0, len(sources) - 1),
    }


class RenderRequest(BaseModel):
    id: str
    headline: str = Field(max_length=70)
    cta: str = Field(default="", max_length=60)


@router.post("/render")
async def render(body: RenderRequest):
    """Vuelve a dibujar la plantilla con el titular/CTA editados (sin gastar cuota de IA)."""
    if not studio.valid_id(body.id):
        raise HTTPException(400, detail={"code": "bad_id", "message": "id inválido"})
    studio.compose_template(studio.source_path(body.id), body.headline, body.cta, studio.composed_path(body.id))
    return {"image_url": f"media/studio/{body.id}.png"}


class SaveRequest(BaseModel):
    id: str | None = None
    content: str = Field(min_length=1, max_length=5000)
    platform: str = "facebook"
    scheduled_at: str | None = None


@router.post("/save")
async def save(body: SaveRequest, db: AsyncSession = Depends(get_db)):
    if body.platform not in ("facebook", "instagram", "all"):
        raise HTTPException(400, detail={"code": "bad_request", "message": "plataforma inválida"})
    image_url = None
    if body.id:
        if not studio.valid_id(body.id) or not studio.composed_path(body.id).is_file():
            raise HTTPException(400, detail={"code": "bad_id", "message": "imagen no encontrada"})
        image_url = f"media/studio/{body.id}.png"
    post = Post(content=body.content, platform=body.platform, image_url=image_url, status="draft")
    if body.scheduled_at:
        try:
            post.scheduled_at = datetime.fromisoformat(body.scheduled_at)
        except ValueError:
            raise HTTPException(400, detail={"code": "bad_date", "message": "fecha inválida"})
        post.status = "scheduled"
    db.add(post)
    await db.commit()
    await db.refresh(post)
    return {"id": post.id, "status": post.status}
