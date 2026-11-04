"""
Lógica del CRM de Felix Software: contactos/leads, avisos al dueño y seguimiento automático.
"""
import logging
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .config import get_settings
from .integrations.facebook import facebook_api
from .integrations.whatsapp import whatsapp_api
from .models import CustomerMessage, Lead

logger = logging.getLogger(__name__)
settings = get_settings()

WINDOW_HOURS = 23  # WhatsApp/Messenger solo permiten texto libre dentro de ~24 h del último mensaje del cliente


async def send_to(platform: str, recipient: str, text: str) -> None:
    """Envía un mensaje por el canal correcto (en modo local queda en la bandeja de salida)."""
    if platform == "whatsapp":
        await whatsapp_api.send_text_message(recipient, text)
    else:
        await facebook_api.send_facebook_message(recipient, text)


async def notify_owner(text: str) -> None:
    """Aviso al dueño por WhatsApp. Si falla (p. ej. fuera de la ventana de 24 h) solo se registra."""
    if not (settings.notify_owner and settings.owner_whatsapp):
        return
    try:
        await whatsapp_api.send_text_message(settings.owner_whatsapp, text)
    except Exception as e:  # noqa: BLE001
        logger.warning("No se pudo avisar al dueño: %s", e)


async def upsert_lead(db: AsyncSession, platform: str, sender_id: str, name: str | None,
                      text: str, wants_booking: bool) -> Lead:
    """Crea o actualiza el contacto. Avisa al dueño cuando un lead nuevo pide agendar/cotizar."""
    lead = (await db.execute(select(Lead).where(Lead.sender_id == sender_id))).scalar_one_or_none()
    now = datetime.utcnow()
    became_booking = False
    if lead is None:
        lead = Lead(platform=platform, sender_id=sender_id, sender_name=name, first_message=text,
                    intent="booking" if wants_booking else "info", last_inbound_at=now)
        db.add(lead)
        became_booking = wants_booking
    else:
        lead.last_inbound_at = now
        if name and not lead.sender_name:
            lead.sender_name = name
        if wants_booking and lead.intent != "booking":
            lead.intent = "booking"
            became_booking = True
    if became_booking:
        who = name or sender_id
        await notify_owner(f"📅 Nuevo interesado en asesoría: {who} ({platform}). Dice: “{text[:140]}”")
    return lead


def _followup_text(name: str | None) -> str:
    hi = f"¡Hola{', ' + name if name else ''}!"
    link = f" Aquí puedes elegir tu horario: {settings.booking_url}" if settings.booking_url else ""
    return (f"{hi} Te escribo de {settings.business_name} para saber si pudiste agendar tu asesoría gratuita 📅.{link}"
            "\n\nSi prefieres, cuéntame tu idea por aquí y te ayudo.")


async def run_followups(db: AsyncSession, force: bool = False, now: datetime | None = None) -> int:
    """
    Seguimiento automático: a quien pidió agendar, sigue en estado "Nuevo" (nadie lo ha atendido a mano)
    y está dentro de la ventana de 24 h. En cuanto tú respondes o cambias el estado, el bot se calla.
    force=True ignora la espera de horas (para probar), pero respeta la ventana y el máximo de seguimientos.
    """
    if not settings.followups_enabled:
        return 0
    now = now or datetime.utcnow()
    wait = timedelta(hours=0 if force else settings.followup_after_hours)
    leads = (await db.execute(
        select(Lead).where(Lead.intent == "booking", Lead.status == "new",
                           Lead.followups_sent < settings.followup_max)
    )).scalars().all()
    sent = 0
    for lead in leads:
        if not lead.last_inbound_at:
            continue
        if now - lead.last_inbound_at > timedelta(hours=WINDOW_HOURS):
            continue  # ventana cerrada: solo plantillas aprobadas por Meta (con costo)
        if now - lead.last_inbound_at < wait:
            continue
        if lead.last_followup_at and now - lead.last_followup_at < wait:
            continue
        text = _followup_text(lead.sender_name)
        try:
            await send_to(lead.platform, lead.sender_id, text)
        except Exception as e:  # noqa: BLE001
            logger.warning("Seguimiento fallido a lead %s: %s", lead.id, e)
            continue
        db.add(CustomerMessage(platform=lead.platform, sender_id=lead.sender_id, sender_name=lead.sender_name,
                               message=text, responded=True, direction="out"))
        lead.followups_sent += 1
        lead.last_followup_at = now
        sent += 1
    await db.commit()
    return sent
