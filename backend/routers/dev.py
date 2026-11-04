"""
Herramientas de desarrollo: simulador de mensajes entrantes y bandeja de salida.
Solo disponible con MOCK_INTEGRATIONS=true.
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import get_settings
from ..crm import run_followups
from ..database import get_db
from ..integrations import outbox as outbox_store
from .webhook import handle_payload

settings = get_settings()


def _only_mock():
    if not settings.mock_integrations:
        raise HTTPException(status_code=404, detail="Solo disponible con MOCK_INTEGRATIONS=true")


router = APIRouter(prefix="/api/dev", tags=["dev"], dependencies=[Depends(_only_mock)])


class Simulate(BaseModel):
    channel: str = "whatsapp"  # whatsapp | facebook
    sender_id: str = "5210000000001"
    name: str = "Cliente de prueba"
    text: str


def whatsapp_payload(sender: str, name: str, text: str) -> dict:
    return {"object": "whatsapp_business_account", "entry": [{"changes": [{"field": "messages", "value": {
        "contacts": [{"profile": {"name": name}}],
        "messages": [{"from": sender, "id": f"wamid.sim{abs(hash(text + sender)) % 10**8}", "type": "text",
                      "timestamp": "0", "text": {"body": text}}]}}]}]}


def messenger_payload(sender: str, text: str) -> dict:
    return {"object": "page", "entry": [{"messaging": [{"sender": {"id": sender}, "message": {"text": text}}]}]}


@router.post("/simulate")
async def simulate(body: Simulate, db: AsyncSession = Depends(get_db)):
    payload = (whatsapp_payload(body.sender_id, body.name, body.text) if body.channel == "whatsapp"
               else messenger_payload(body.sender_id, body.text))
    return await handle_payload(payload, db)


@router.get("/outbox")
async def outbox(limit: int = 50):
    return outbox_store.latest(limit)


@router.delete("/outbox")
async def clear_outbox():
    outbox_store.clear()
    return {"cleared": True}


@router.post("/run-followups")
async def followups(force: bool = True, db: AsyncSession = Depends(get_db)):
    return {"sent": await run_followups(db, force=force)}
