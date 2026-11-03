"""
Leads: personas que mostraron interés en agendar o cotizar.
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from ..database import get_db
from ..models import Lead

router = APIRouter(prefix="/api/leads", tags=["leads"])
_STATUSES = {"new", "contacted", "scheduled", "won", "lost"}


class UpdateLead(BaseModel):
    status: str | None = None
    notes: str | None = None


@router.get("/")
async def list_leads(status: str | None = None, db: AsyncSession = Depends(get_db)):
    q = select(Lead).order_by(desc(Lead.created_at))
    if status:
        q = q.where(Lead.status == status)
    return [
        {"id": l.id, "platform": l.platform, "sender_id": l.sender_id, "sender_name": l.sender_name,
         "first_message": l.first_message, "status": l.status, "notes": l.notes,
         "created_at": l.created_at.isoformat()}
        for l in (await db.execute(q)).scalars().all()
    ]


@router.patch("/{lead_id}")
async def update_lead(lead_id: int, body: UpdateLead, db: AsyncSession = Depends(get_db)):
    lead = (await db.execute(select(Lead).where(Lead.id == lead_id))).scalar_one_or_none()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead no encontrado")
    if body.status is not None:
        if body.status not in _STATUSES:
            raise HTTPException(status_code=400, detail=f"Estado inválido. Usa: {sorted(_STATUSES)}")
        lead.status = body.status
    if body.notes is not None:
        lead.notes = body.notes
    await db.commit()
    return {"id": lead.id, "status": lead.status}
