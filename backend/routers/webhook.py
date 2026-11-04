"""
Webhook de Meta para recibir mensajes de WhatsApp y Facebook en tiempo real.
Usa el agente especializado que maneja KB y tickets de ayuda.
"""
import hashlib
import hmac
import json
import logging
from fastapi import APIRouter, Request, Response, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc

from ..database import get_db
from ..models import CustomerMessage, HelpTicket
from ..agents.response_agent import process_customer_message, should_auto_respond
from ..integrations.whatsapp import whatsapp_api
from ..crm import send_to, notify_owner, upsert_lead
from ..config import get_settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/webhook", tags=["webhook"])
settings = get_settings()


@router.get("/meta")
async def verify_webhook(request: Request):
    """Verificación del webhook de Meta (handshake inicial)."""
    params = dict(request.query_params)
    if (params.get("hub.mode") == "subscribe"
            and params.get("hub.verify_token") == settings.meta_webhook_verify_token):
        return Response(content=params.get("hub.challenge"), media_type="text/plain")
    raise HTTPException(status_code=403, detail="Token de verificación inválido")


@router.post("/meta")
async def receive_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    """Recibe mensajes de clientes vía WhatsApp o Facebook Messenger."""
    raw = await request.body()
    if settings.meta_app_secret:
        sent = request.headers.get("x-hub-signature-256", "")
        expected = "sha256=" + hmac.new(settings.meta_app_secret.encode(), raw, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sent, expected):
            raise HTTPException(status_code=403, detail="Firma inválida")
    elif not settings.mock_integrations:
        logger.warning("META_APP_SECRET vacío: el webhook acepta mensajes sin verificar su origen")
    return await handle_payload(json.loads(raw or b"{}"), db)


async def _handle_inbound(db: AsyncSession, platform: str, sender_id: str, name: str | None, text: str) -> None:
    """Flujo común: registrar -> agente (KB/IA) -> responder -> CRM -> ticket."""
    if not await should_auto_respond(text):
        return
    customer_msg = CustomerMessage(platform=platform, sender_id=sender_id, sender_name=name, message=text)
    result = await process_customer_message(customer_message=text, db=db, platform=platform)

    try:
        await send_to(platform, sender_id, result.response_text)
        customer_msg.response = result.response_text
        customer_msg.responded = True
    except Exception as e:  # noqa: BLE001
        customer_msg.response = f"[Error al enviar: {e}]"
    db.add(customer_msg)

    await upsert_lead(db, platform, sender_id, name, text, result.wants_booking)

    if result.needs_ticket:
        db.add(HelpTicket(platform=platform, sender_id=sender_id, sender_name=name,
                          original_message=text, extracted_question=result.ticket_question))
        await notify_owner(f"🎫 Duda nueva de {name or sender_id}: {result.ticket_question}")


async def handle_payload(body: dict, db: AsyncSession) -> dict:
    object_type = body.get("object", "")

    if object_type == "whatsapp_business_account":
        for entry in body.get("entry", []):
            for change in entry.get("changes", []):
                if change.get("field") != "messages":
                    continue
                parsed = whatsapp_api.parse_incoming_message(
                    {"entry": [{"changes": [{"value": change.get("value", {})}]}]}
                )
                if not parsed:
                    continue
                try:
                    await whatsapp_api.mark_as_read(parsed["message_id"])
                except Exception:  # noqa: BLE001
                    pass
                await _handle_inbound(db, "whatsapp", parsed["sender_phone"],
                                      parsed.get("sender_name", "Cliente"), parsed["text"])

    elif object_type == "page":
        for entry in body.get("entry", []):
            for messaging in entry.get("messaging", []):
                sender_id = messaging.get("sender", {}).get("id")
                text = messaging.get("message", {}).get("text")
                if sender_id and text:
                    await _handle_inbound(db, "facebook", sender_id, None, text)

    await db.commit()
    return {"status": "ok"}


@router.get("/messages")
async def get_customer_messages(
    platform: str | None = None,
    limit: int = 50,
    db: AsyncSession = Depends(get_db)
):
    """Lista los mensajes de clientes recibidos."""
    query = select(CustomerMessage).order_by(desc(CustomerMessage.created_at)).limit(limit)
    if platform:
        query = query.where(CustomerMessage.platform == platform)
    result = await db.execute(query)
    messages = result.scalars().all()
    return [
        {
            "id": m.id,
            "platform": m.platform,
            "sender_id": m.sender_id,
            "sender_name": m.sender_name,
            "message": m.message,
            "response": m.response,
            "responded": m.responded,
            "direction": m.direction,
            "created_at": m.created_at.isoformat()
        }
        for m in messages
    ]
