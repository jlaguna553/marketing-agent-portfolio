"""
CRM: contactos/leads, conversación por contacto, respuesta manual y métricas.
"""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, desc, func
from sqlalchemy.ext.asyncio import AsyncSession

from ..crm import send_to
from ..database import get_db
from ..models import CustomerMessage, Lead

router = APIRouter(prefix="/api/leads", tags=["crm"])
STATUSES = ["new", "contacted", "scheduled", "won", "lost"]


class UpdateLead(BaseModel):
    status: str | None = None
    notes: str | None = None


class ReplyBody(BaseModel):
    text: str


def _lead_dict(l: Lead) -> dict:
    return {"id": l.id, "platform": l.platform, "sender_id": l.sender_id, "sender_name": l.sender_name,
            "first_message": l.first_message, "status": l.status, "intent": l.intent, "notes": l.notes,
            "followups_sent": l.followups_sent,
            "last_inbound_at": l.last_inbound_at.isoformat() if l.last_inbound_at else None,
            "created_at": l.created_at.isoformat()}


@router.get("/stats")
async def stats(db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(select(Lead.status, func.count()).group_by(Lead.status))).all()
    by_status = {s: 0 for s in STATUSES}
    by_status.update({s: n for s, n in rows})
    booking = (await db.execute(select(func.count()).select_from(Lead).where(Lead.intent == "booking"))).scalar_one()
    return {"total": sum(by_status.values()), "by_status": by_status, "booking_intent": booking}


@router.get("/")
async def list_leads(status: str | None = None, db: AsyncSession = Depends(get_db)):
    q = select(Lead).order_by(desc(Lead.last_inbound_at), desc(Lead.created_at))
    if status:
        q = q.where(Lead.status == status)
    return [_lead_dict(l) for l in (await db.execute(q)).scalars().all()]


@router.get("/{lead_id}")
async def lead_detail(lead_id: int, db: AsyncSession = Depends(get_db)):
    lead = (await db.execute(select(Lead).where(Lead.id == lead_id))).scalar_one_or_none()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead no encontrado")
    msgs = (await db.execute(
        select(CustomerMessage).where(CustomerMessage.sender_id == lead.sender_id).order_by(CustomerMessage.created_at, CustomerMessage.id)
    )).scalars().all()
    thread = []
    for m in msgs:
        if m.direction == "out":
            thread.append({"from": "owner", "text": m.message, "at": m.created_at.isoformat()})
        else:
            thread.append({"from": "client", "text": m.message, "at": m.created_at.isoformat()})
            if m.response:
                thread.append({"from": "bot", "text": m.response, "at": m.created_at.isoformat()})
    return {**_lead_dict(lead), "thread": thread}


@router.patch("/{lead_id}")
async def update_lead(lead_id: int, body: UpdateLead, db: AsyncSession = Depends(get_db)):
    lead = (await db.execute(select(Lead).where(Lead.id == lead_id))).scalar_one_or_none()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead no encontrado")
    if body.status is not None:
        if body.status not in STATUSES:
            raise HTTPException(status_code=400, detail=f"Estado inválido. Usa: {STATUSES}")
        lead.status = body.status
    if body.notes is not None:
        lead.notes = body.notes
    await db.commit()
    return _lead_dict(lead)


@router.post("/{lead_id}/reply")
async def reply_to_lead(lead_id: int, body: ReplyBody, db: AsyncSession = Depends(get_db)):
    """Respuesta manual del dueño desde el CRM; marca el lead como 'contactado' si estaba nuevo."""
    text = body.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="El mensaje está vacío")
    lead = (await db.execute(select(Lead).where(Lead.id == lead_id))).scalar_one_or_none()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead no encontrado")
    try:
        await send_to(lead.platform, lead.sender_id, text)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"No se pudo enviar: {e}")
    db.add(CustomerMessage(platform=lead.platform, sender_id=lead.sender_id, sender_name=lead.sender_name,
                           message=text, responded=True, direction="out"))
    if lead.status == "new":
        lead.status = "contacted"
    await db.commit()
    return {"sent": True, "status": lead.status}
