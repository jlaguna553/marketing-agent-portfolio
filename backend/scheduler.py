"""
Scheduler para publicación automática de posts programados.
Usa APScheduler para revisar cada minuto si hay posts listos para publicar.
"""
from datetime import datetime, timezone
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy import select
from .database import AsyncSessionLocal
from .models import Post
from .integrations.facebook import facebook_api
import logging

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()


async def publish_scheduled_posts():
    """
    Revisa los posts programados y publica los que ya llegaron a su hora.
    Se ejecuta cada minuto.
    """
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Post).where(
                Post.status == "scheduled",
                Post.scheduled_at <= now
            )
        )
        posts = result.scalars().all()

        for post in posts:
            logger.info(f"Publicando post programado ID={post.id} en {post.platform}")
            errors = []

            if post.platform in ("facebook", "all"):
                try:
                    resp = await facebook_api.publish_facebook_post(post.content, post.image_url)
                    post.external_id = str(resp.get("id") or resp.get("post_id", ""))
                except Exception as e:
                    errors.append(f"Facebook: {e}")

            if post.platform in ("instagram", "all") and (post.image_url or "").startswith(("http://", "https://")):  # IG exige URL pública
                try:
                    await facebook_api.publish_instagram_post(post.content, post.image_url)
                except Exception as e:
                    errors.append(f"Instagram: {e}")

            if errors and not post.external_id:
                post.status = "failed"
                post.error_message = "; ".join(errors)
                logger.error(f"Post ID={post.id} falló: {post.error_message}")
            else:
                post.status = "published"
                post.published_at = datetime.utcnow()
                logger.info(f"Post ID={post.id} publicado correctamente")

        await db.commit()


def start_scheduler():
    """Inicia el scheduler de publicación automática."""
    scheduler.add_job(
        publish_scheduled_posts,
        trigger=IntervalTrigger(minutes=1),
        id="publish_scheduled_posts",
        replace_existing=True
    )
    scheduler.start()
    logger.info("Scheduler de publicaciones iniciado (intervalo: 1 minuto)")


def stop_scheduler():
    """Detiene el scheduler."""
    if scheduler.running:
        scheduler.shutdown()
