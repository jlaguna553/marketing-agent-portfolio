"""
Router para tickets de ayuda y base de conocimiento.

Tickets: preguntas que el agente no pudo responder — el operador las ve aquí,
         escribe la respuesta, y el sistema la envía al cliente y la guarda en la KB.

Knowledge Base (KB): compendio de preguntas/respuestas del negocio.
                     Se alimenta manualmente o automáticamente desde tickets resueltos.
"""
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc, func

from ..database import get_db
from ..models import HelpTicket, KnowledgeBase
from ..integrations.whatsapp import whatsapp_api
from ..integrations.facebook import facebook_api

router = APIRouter(prefix="/api/tickets", tags=["tickets"])


# ── Tickets ───────────────────────────────────────────────────

@router.get("/")
async def list_tickets(
    status: str = "open",
    limit: int = 50,
    db: AsyncSession = Depends(get_db)
):
    """Lista tickets filtrando por status (open | answered | dismissed | all)."""
    query = select(HelpTicket).order_by(desc(HelpTicket.created_at)).limit(limit)
    if status != "all":
        query = query.where(HelpTicket.status == status)
    result = await db.execute(query)
    tickets = result.scalars().all()
    return [_ticket_to_dict(t) for t in tickets]


@router.get("/count")
async def count_open_tickets(db: AsyncSession = Depends(get_db)):
    """Cuenta tickets abiertos — para el badge en la UI."""
    result = await db.execute(
        select(func.count()).where(HelpTicket.status == "open")
    )
    return {"open": result.scalar_one()}


class AnswerTicketRequest(BaseModel):
    answer: str
    save_to_kb: bool = True


@router.post("/{ticket_id}/answer")
async def answer_ticket(
    ticket_id: int,
    body: AnswerTicketRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    El operador responde un ticket.
    1. Guarda la respuesta en el ticket
    2. Envía la respuesta al cliente por WhatsApp o Facebook
    3. Si save_to_kb=True, agrega la pregunta/respuesta a la KB
    """
    result = await db.execute(select(HelpTicket).where(HelpTicket.id == ticket_id))
    ticket = result.scalar_one_or_none()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket no encontrado")
    if ticket.status == "answered":
        raise HTTPException(status_code=400, detail="El ticket ya fue respondido")

    ticket.operator_answer = body.answer
    ticket.status = "answered"
    ticket.answered_at = datetime.utcnow()

    send_error = None
    try:
        if ticket.platform == "whatsapp":
            await whatsapp_api.send_text_message(ticket.sender_id, body.answer)
        elif ticket.platform == "facebook":
            await facebook_api.send_facebook_message(ticket.sender_id, body.answer)
        ticket.answer_sent = True
    except Exception as e:
        send_error = str(e)

    # Guardar en KB
    if body.save_to_kb and body.answer.strip():
        kb_entry = KnowledgeBase(
            question=ticket.extracted_question,
            answer=body.answer.strip(),
            category="general",
        )
        db.add(kb_entry)

    await db.commit()
    return {
        "status": "answered",
        "answer_sent": ticket.answer_sent,
        "send_error": send_error,
        "kb_saved": body.save_to_kb,
    }


@router.post("/{ticket_id}/dismiss")
async def dismiss_ticket(ticket_id: int, db: AsyncSession = Depends(get_db)):
    """Descarta un ticket sin responder (duplicado, spam, etc.)."""
    result = await db.execute(select(HelpTicket).where(HelpTicket.id == ticket_id))
    ticket = result.scalar_one_or_none()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket no encontrado")
    ticket.status = "dismissed"
    await db.commit()
    return {"status": "dismissed"}


# ── Knowledge Base ────────────────────────────────────────────

kb_router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])


class KBEntryRequest(BaseModel):
    question: str
    answer: str
    category: str = "general"


@kb_router.get("/")
async def list_kb(db: AsyncSession = Depends(get_db)):
    """Lista toda la base de conocimiento."""
    result = await db.execute(
        select(KnowledgeBase).order_by(KnowledgeBase.category, KnowledgeBase.id)
    )
    entries = result.scalars().all()
    return [_kb_to_dict(e) for e in entries]


@kb_router.post("/")
async def add_kb_entry(body: KBEntryRequest, db: AsyncSession = Depends(get_db)):
    """Agrega una entrada manualmente a la KB."""
    entry = KnowledgeBase(
        question=body.question.strip(),
        answer=body.answer.strip(),
        category=body.category.lower(),
    )
    db.add(entry)
    await db.commit()
    await db.refresh(entry)
    return _kb_to_dict(entry)


@kb_router.put("/{entry_id}")
async def update_kb_entry(
    entry_id: int,
    body: KBEntryRequest,
    db: AsyncSession = Depends(get_db)
):
    """Actualiza una entrada de la KB."""
    result = await db.execute(select(KnowledgeBase).where(KnowledgeBase.id == entry_id))
    entry = result.scalar_one_or_none()
    if not entry:
        raise HTTPException(status_code=404, detail="Entrada no encontrada")
    entry.question = body.question.strip()
    entry.answer = body.answer.strip()
    entry.category = body.category.lower()
    entry.updated_at = datetime.utcnow()
    await db.commit()
    return _kb_to_dict(entry)


@kb_router.delete("/{entry_id}")
async def delete_kb_entry(entry_id: int, db: AsyncSession = Depends(get_db)):
    """Elimina una entrada de la KB."""
    result = await db.execute(select(KnowledgeBase).where(KnowledgeBase.id == entry_id))
    entry = result.scalar_one_or_none()
    if not entry:
        raise HTTPException(status_code=404, detail="Entrada no encontrada")
    await db.delete(entry)
    await db.commit()
    return {"deleted": True}


# ── Helpers ───────────────────────────────────────────────────

def _ticket_to_dict(t: HelpTicket) -> dict:
    return {
        "id": t.id,
        "platform": t.platform,
        "sender_id": t.sender_id,
        "sender_name": t.sender_name,
        "original_message": t.original_message,
        "extracted_question": t.extracted_question,
        "status": t.status,
        "operator_answer": t.operator_answer,
        "answer_sent": t.answer_sent,
        "created_at": t.created_at.isoformat(),
        "answered_at": t.answered_at.isoformat() if t.answered_at else None,
    }


def _kb_to_dict(e: KnowledgeBase) -> dict:
    return {
        "id": e.id,
        "question": e.question,
        "answer": e.answer,
        "category": e.category,
        "times_used": e.times_used,
        "created_at": e.created_at.isoformat(),
    }
