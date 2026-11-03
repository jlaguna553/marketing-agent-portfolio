"""
Integración con Meta Graph API para publicar en Facebook e Instagram.
Documentación: https://developers.facebook.com/docs/graph-api
"""
from pathlib import Path
import httpx
from ..config import get_settings
from . import outbox

settings = get_settings()

GRAPH_API_BASE = "https://graph.facebook.com/v21.0"


class FacebookAPI:
    def __init__(self):
        self.token = settings.meta_access_token
        self.page_id = settings.facebook_page_id
        self.ig_account_id = settings.instagram_account_id

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.token}"}

    async def publish_facebook_post(self, message: str, image_url: str | None = None) -> dict:
        """
        Publica un post en la página de Facebook.
        Retorna el ID del post creado.
        """
        if settings.mock_integrations:
            await outbox.record("facebook", "post", message + (f"\n[imagen: {image_url}]" if image_url else ""))
            return {"id": outbox.fake_id("fbpost")}
        url = f"{GRAPH_API_BASE}/{self.page_id}/feed"
        payload: dict = {"message": message, "access_token": self.token}

        # Imagen local (carpeta media/): se sube directo, sin necesitar hosting público.
        if image_url and not image_url.startswith(("http://", "https://")):
            path = Path(image_url).resolve()
            if not path.is_file() or Path("media").resolve() not in path.parents:
                raise ValueError(f"Imagen local no válida (debe estar dentro de media/): {image_url}")
            async with httpx.AsyncClient(timeout=60) as client:
                with path.open("rb") as fh:
                    response = await client.post(
                        f"{GRAPH_API_BASE}/{self.page_id}/photos",
                        data={"caption": message, "access_token": self.token},
                        files={"source": (path.name, fh, "image/png")},
                    )
                response.raise_for_status()
                return response.json()

        if image_url:
            url = f"{GRAPH_API_BASE}/{self.page_id}/photos"
            payload["url"] = image_url
            payload["caption"] = message

        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(url, data=payload)
            response.raise_for_status()
            return response.json()

    async def publish_instagram_post(self, caption: str, image_url: str) -> dict:
        """
        Publica un post en Instagram.
        Requiere una imagen (Instagram no permite posts solo texto).
        Retorna el ID del post creado.
        """
        if settings.mock_integrations:
            await outbox.record("instagram", "post", f"{caption}\n[imagen: {image_url}]")
            return {"id": outbox.fake_id("igpost")}
        async with httpx.AsyncClient(timeout=60) as client:
            # Paso 1: Crear container de media
            container_url = f"{GRAPH_API_BASE}/{self.ig_account_id}/media"
            container_payload = {
                "image_url": image_url,
                "caption": caption,
                "access_token": self.token
            }
            container_response = await client.post(container_url, data=container_payload)
            container_response.raise_for_status()
            container_id = container_response.json()["id"]

            # Paso 2: Publicar el container
            publish_url = f"{GRAPH_API_BASE}/{self.ig_account_id}/media_publish"
            publish_payload = {
                "creation_id": container_id,
                "access_token": self.token
            }
            publish_response = await client.post(publish_url, data=publish_payload)
            publish_response.raise_for_status()
            return publish_response.json()

    async def reply_to_comment(self, comment_id: str, message: str) -> dict:
        """Responde a un comentario en Facebook."""
        url = f"{GRAPH_API_BASE}/{comment_id}/comments"
        payload = {"message": message, "access_token": self.token}
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(url, data=payload)
            response.raise_for_status()
            return response.json()

    async def send_facebook_message(self, recipient_id: str, message: str) -> dict:
        """Envía un mensaje por Facebook Messenger."""
        if settings.mock_integrations:
            await outbox.record("facebook", "message", message, recipient_id)
            return {"message_id": outbox.fake_id("mid")}
        url = f"{GRAPH_API_BASE}/me/messages"
        payload = {
            "recipient": {"id": recipient_id},
            "message": {"text": message},
            "access_token": self.token
        }
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            return response.json()

    async def get_page_insights(self) -> dict:
        """Obtiene métricas básicas de la página."""
        url = f"{GRAPH_API_BASE}/{self.page_id}/insights"
        params = {
            "metric": "page_fans,page_impressions,page_engaged_users",
            "period": "day",
            "access_token": self.token
        }
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            return response.json()


facebook_api = FacebookAPI()
