"""
Webhook de Meta para recibir mensajes de WhatsApp y Facebook en tiempo real.
Usa el agente especializado que maneja KB y tickets de ayuda.
"""
from fastapi import APIRouter, Request, Response, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc

from ..database import get_db
from ..models import CustomerMessage, HelpTicket, Lead
from ..agents.response_agent import process_customer_message, should_auto_respond
from ..integrations.whatsapp import whatsapp_api
from ..integrations.facebook import facebook_api
from ..config import get_settings

router = APIRouter(prefix="/webhook", tags=["webhook"])
settings = get_settings()


async def _capture_lead(db: AsyncSession, platform: str, sender_id: str, name: str | None, text: str) -> None:
    """Registra un lead una sola vez por remitente cuando muestra interés en agendar/cotizar."""
    exists = (await db.execute(select(Lead.id).where(Lead.sender_id == sender_id))).first()
    if not exists:
        db.add(Lead(platform=platform, sender_id=sender_id, sender_name=name, first_message=text))


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
    """
    Recibe mensajes de clientes vía WhatsApp o Facebook.
    Flujo:
      1. Parsear mensaje entrante
      2. Llamar al agente (KB + detección de ticket)
      3. Si el agente puede responder → enviar al cliente
      4. Si el agente necesita ayuda → crear ticket + enviar "te consulto" al cliente
    """
    body = await request.json()
    object_type = body.get("object", "")

    # ── WhatsApp ──────────────────────────────────────────────
    if object_type == "whatsapp_business_account":
        for entry in body.get("entry", []):
            for change in entry.get("changes", []):
                if change.get("field") != "messages":
                    continue
                value = change.get("value", {})
                parsed = whatsapp_api.parse_incoming_message(
                    {"entry": [{"changes": [{"value": value}]}]}
                )
                if not parsed:
                    continue

                sender_phone = parsed["sender_phone"]
                sender_name = parsed.get("sender_name", "Cliente")
                message_text = parsed["text"]
                message_id = parsed["message_id"]

                # Marcar como leído
                try:
                    await whatsapp_api.mark_as_read(message_id)
                except Exception:
                    pass

                if not await should_auto_respond(message_text):
                    continue

                # Registrar mensaje del cliente
                customer_msg = CustomerMessage(
                    platform="whatsapp",
                    sender_id=sender_phone,
                    sender_name=sender_name,
                    message=message_text,
                )

                # Procesar con el agente (KB + ticket)
                result = await process_customer_message(
                    customer_message=message_text,
                    db=db,
                    platform="whatsapp",
                )

                # Enviar respuesta al cliente
                try:
                    await whatsapp_api.send_text_message(sender_phone, result.response_text)
                    customer_msg.response = result.response_text
                    customer_msg.responded = True
                except Exception as e:
                    customer_msg.response = f"[Error al enviar: {e}]"

                db.add(customer_msg)

                if result.wants_booking:
                    await _capture_lead(db, "whatsapp", sender_phone, sender_name, message_text)

                # Crear ticket si el agente no pudo responder
                if result.needs_ticket:
                    ticket = HelpTicket(
                        platform="whatsapp",
                        sender_id=sender_phone,
                        sender_name=sender_name,
                        original_message=message_text,
                        extracted_question=result.ticket_question,
                    )
                    db.add(ticket)

    # ── Facebook Messenger ────────────────────────────────────
    elif object_type == "page":
        for entry in body.get("entry", []):
            for messaging in entry.get("messaging", []):
                sender_id = messaging.get("sender", {}).get("id")
                message_obj = messaging.get("message", {})
                message_text = message_obj.get("text")

                if not sender_id or not message_text:
                    continue
                if not await should_auto_respond(message_text):
                    continue

                customer_msg = CustomerMessage(
                    platform="facebook",
                    sender_id=sender_id,
                    message=message_text,
                )

                result = await process_customer_message(
                    customer_message=message_text,
                    db=db,
                    platform="facebook",
                )

                try:
                    await facebook_api.send_facebook_message(sender_id, result.response_text)
                    customer_msg.response = result.response_text
                    customer_msg.responded = True
                except Exception as e:
                    customer_msg.response = f"[Error al enviar: {e}]"

                db.add(customer_msg)

                if result.wants_booking:
                    await _capture_lead(db, "facebook", sender_id, None, message_text)

                if result.needs_ticket:
                    ticket = HelpTicket(
                        platform="facebook",
                        sender_id=sender_id,
                        original_message=message_text,
                        extracted_question=result.ticket_question,
                    )
                    db.add(ticket)

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
            "created_at": m.created_at.isoformat()
        }
        for m in messages
    ]
