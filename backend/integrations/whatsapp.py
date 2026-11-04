"""
Integración con WhatsApp Business API (Cloud API de Meta).
Documentación: https://developers.facebook.com/docs/whatsapp/cloud-api
"""
import logging
import httpx
from ..config import get_settings
from . import outbox

logger = logging.getLogger(__name__)

settings = get_settings()

WHATSAPP_API_BASE = "https://graph.facebook.com/v21.0"


class WhatsAppAPI:
    def __init__(self):
        self.phone_number_id = settings.whatsapp_phone_number_id
        self.token = settings.whatsapp_access_token

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json"
        }

    @staticmethod
    def normalize_phone(phone: str) -> str:
        """
        Normaliza números mexicanos: WhatsApp envía 5214XXXXXXXXXX (13 dígitos)
        pero la API de envío requiere 524XXXXXXXXXX (12 dígitos).
        Elimina el '1' de móvil que WhatsApp agrega automáticamente.
        """
        phone = phone.lstrip("+")
        # México: 52 + 1 + 10 dígitos = 13 → quitar el 1
        if len(phone) == 13 and phone.startswith("521"):
            phone = "52" + phone[3:]
        return phone

    async def send_text_message(self, to: str, message: str) -> dict:
        """
        Envía un mensaje de texto por WhatsApp.
        Args:
            to: Número de teléfono del destinatario (formato internacional, ej: 524612172611)
            message: Texto del mensaje
        """
        to_clean = self.normalize_phone(to)
        if settings.mock_integrations:
            await outbox.record("whatsapp", "message", message, to_clean)
            return {"messages": [{"id": outbox.fake_id("wamid")}]}
        url = f"{WHATSAPP_API_BASE}/{self.phone_number_id}/messages"
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to_clean,
            "type": "text",
            "text": {"preview_url": False, "body": message}
        }
        logger.info(f"Enviando WhatsApp a {to_clean}: {message[:60]}...")
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(url, json=payload, headers=self._headers())
            if response.status_code != 200:
                logger.error(f"WhatsApp API error {response.status_code}: {response.text}")
            response.raise_for_status()
            return response.json()

    async def send_image_message(self, to: str, image_url: str, caption: str = "") -> dict:
        """Envía una imagen con caption por WhatsApp."""
        url = f"{WHATSAPP_API_BASE}/{self.phone_number_id}/messages"
        payload = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "image",
            "image": {"link": image_url, "caption": caption}
        }
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(url, json=payload, headers=self._headers())
            response.raise_for_status()
            return response.json()

    async def send_template_message(self, to: str, template_name: str, language: str = "es") -> dict:
        """Envía un mensaje usando una plantilla pre-aprobada por Meta."""
        url = f"{WHATSAPP_API_BASE}/{self.phone_number_id}/messages"
        payload = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "template",
            "template": {
                "name": template_name,
                "language": {"code": language}
            }
        }
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(url, json=payload, headers=self._headers())
            response.raise_for_status()
            return response.json()

    async def mark_as_read(self, message_id: str) -> dict:
        """Marca un mensaje como leído."""
        if settings.mock_integrations:
            return {"success": True}
        url = f"{WHATSAPP_API_BASE}/{self.phone_number_id}/messages"
        payload = {
            "messaging_product": "whatsapp",
            "status": "read",
            "message_id": message_id
        }
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(url, json=payload, headers=self._headers())
            response.raise_for_status()
            return response.json()

    def parse_incoming_message(self, webhook_data: dict) -> dict | None:
        """
        Parsea el payload del webhook de WhatsApp.
        Retorna dict con sender, message_id, text o None si no es mensaje de texto.
        """
        try:
            entry = webhook_data["entry"][0]
            changes = entry["changes"][0]
            value = changes["value"]

            if "messages" not in value:
                return None

            message = value["messages"][0]
            if message["type"] != "text":
                return None

            contact = value["contacts"][0] if "contacts" in value else {}

            return {
                "sender_phone": message["from"],
                "sender_name": contact.get("profile", {}).get("name", "Cliente"),
                "message_id": message["id"],
                "text": message["text"]["body"],
                "timestamp": message["timestamp"]
            }
        except (KeyError, IndexError):
            return None


whatsapp_api = WhatsAppAPI()
