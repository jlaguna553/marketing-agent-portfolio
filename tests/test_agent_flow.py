import pytest
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from backend.database import Base
from backend.models import KnowledgeBase
from backend.agents.response_agent import process_customer_message


@pytest.mark.asyncio
async def test_kb_y_saludo_no_llaman_al_llm(monkeypatch):
    async def boom(*a, **k):
        raise AssertionError("No debía llamar al LLM")
    monkeypatch.setattr("backend.agents.response_agent._anthropic_complete", boom)

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as c:
        await c.run_sync(Base.metadata.create_all)
    async with async_sessionmaker(engine, expire_on_commit=False)() as db:
        db.add(KnowledgeBase(question="¿Qué es CaaS?", answer="Software a tu medida con renta mensual."))
        await db.commit()
        r = await process_customer_message("hola", db)
        assert r.source == "greeting"
        r = await process_customer_message("que es caas", db)
        assert r.source == "kb" and "renta mensual" in r.response_text
        r = await process_customer_message("quiero agendar una asesoria", db)
        assert r.wants_booking
