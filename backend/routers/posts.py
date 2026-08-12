"""
Router para gestión de posts: listar, crear, publicar, eliminar.
"""
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc

from ..database import get_db
from ..models import Post
from ..integrations.facebook import facebook_api

router = APIRouter(prefix="/api/posts", tags=["posts"])


class CreatePostRequest(BaseModel):
    content: str
    platform: str = "all"
    image_url: str | None = None
    scheduled_at: str | None = None


class PublishPostRequest(BaseModel):
    post_id: int


@router.get("/")
async def list_posts(
    status: str | None = None,
    limit: int = 20,
    db: AsyncSession = Depends(get_db)
):
    """Lista todos los posts, opcionalmente filtrados por status."""
    query = select(Post).order_by(desc(Post.created_at)).limit(limit)
    if status:
        query = query.where(Post.status == status)
    result = await db.execute(query)
    posts = result.scalars().all()
    return [
        {
            "id": p.id,
            "content": p.content,
            "platform": p.platform,
            "status": p.status,
            "image_url": p.image_url,
            "scheduled_at": p.scheduled_at.isoformat() if p.scheduled_at else None,
            "published_at": p.published_at.isoformat() if p.published_at else None,
            "created_at": p.created_at.isoformat(),
            "error_message": p.error_message
        }
        for p in posts
    ]


@router.post("/")
async def create_post(body: CreatePostRequest, db: AsyncSession = Depends(get_db)):
    """Crea un post como borrador o programado."""
    post = Post(
        content=body.content,
        platform=body.platform,
        image_url=body.image_url,
        status="draft"
    )
    if body.scheduled_at:
        post.scheduled_at = datetime.fromisoformat(body.scheduled_at)
        post.status = "scheduled"

    db.add(post)
    await db.commit()
    await db.refresh(post)
    return {"id": post.id, "status": post.status}


@router.post("/{post_id}/publish")
async def publish_post(post_id: int, db: AsyncSession = Depends(get_db)):
    """Publica un post guardado en las redes configuradas."""
    result = await db.execute(select(Post).where(Post.id == post_id))
    post = result.scalar_one_or_none()
    if not post:
        raise HTTPException(status_code=404, detail="Post no encontrado")
    if post.status == "published":
        raise HTTPException(status_code=400, detail="El post ya fue publicado")

    published_ids = {}
    errors = []

    if post.platform in ("facebook", "all"):
        try:
            resp = await facebook_api.publish_facebook_post(post.content, post.image_url)
            published_ids["facebook"] = resp.get("id") or resp.get("post_id")
        except Exception as e:
            errors.append(f"Facebook: {e}")

    if post.platform in ("instagram", "all") and post.image_url:
        try:
            resp = await facebook_api.publish_instagram_post(post.content, post.image_url)
            published_ids["instagram"] = resp.get("id")
        except Exception as e:
            errors.append(f"Instagram: {e}")

    if errors and not published_ids:
        post.status = "failed"
        post.error_message = "; ".join(errors)
    else:
        post.status = "published"
        post.published_at = datetime.utcnow()
        if published_ids:
            post.external_id = str(published_ids)

    await db.commit()
    return {"status": post.status, "published_ids": published_ids, "errors": errors}


@router.delete("/{post_id}")
async def delete_post(post_id: int, db: AsyncSession = Depends(get_db)):
    """Elimina un post (solo si no está publicado)."""
    result = await db.execute(select(Post).where(Post.id == post_id))
    post = result.scalar_one_or_none()
    if not post:
        raise HTTPException(status_code=404, detail="Post no encontrado")
    if post.status == "published":
        raise HTTPException(status_code=400, detail="No se puede eliminar un post ya publicado")
    await db.delete(post)
    await db.commit()
    return {"deleted": True}
