import importlib
import json
import sqlite3
import sys
from types import SimpleNamespace as NS

import pytest

KB = [
    ("¿Qué es CaaS?", "Software a tu medida con renta mensual.", "servicios"),
    ("¿Cuánto cuesta una página web?", "Desde $1,000 MXN al mes.", "precios"),
    ("¿Cuánto cuesta un sistema a medida?", "Desde $2,500 MXN al mes.", "precios"),
    ("¿Tienen punto de venta?", "Sí: órdenes, cocina, inventario, recetas, caja.", "proyectos"),
    ("¿Hacen recordatorios por WhatsApp?", "Sí, recurrentes y con plantillas e imágenes.", "proyectos"),
    ("¿Hacen sistemas para escuelas?", "Sí, con calificaciones y facturación.", "proyectos"),
    ("¿Cómo funciona la asesoría?", "Una videollamada corta y gratuita para conocer tu idea.", "asesoria"),
    ("¿Dan soporte después de entregar?", "Sí, el mantenimiento va incluido en la renta mensual.", "soporte"),
]


@pytest.fixture()
async def env(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path}/r.db")
    monkeypatch.setenv("LLM_PROVIDER", "workers_ai")
    monkeypatch.setenv("CF_ACCOUNT_ID", "acct")
    monkeypatch.setenv("CF_API_TOKEN", "tok")
    for m in [m for m in sys.modules if m == "main" or m.startswith("backend")]:
        del sys.modules[m]
    from backend.database import init_db, AsyncSessionLocal
    from backend.models import KnowledgeBase
    await init_db()
    async with AsyncSessionLocal() as db:
        for q, a, c in KB:
            db.add(KnowledgeBase(question=q, answer=a, category=c))
        await db.commit()
    mods = NS(
        agent=importlib.import_module("backend.agents.response_agent"),
        wai=importlib.import_module("backend.workers_ai"),
        rag=importlib.import_module("backend.rag"),
        usage=importlib.import_module("backend.usage"),
        settings=importlib.import_module("backend.config").get_settings(),
        Session=AsyncSessionLocal,
    )
    mods.usage.reset()
    return mods


async def test_prompt_lleva_solo_las_entradas_relevantes(env, monkeypatch):
    seen = {}

    async def fake_complete(system, messages, model, max_tokens=350):
        seen["system"], seen["model"] = system, model
        return "Sí, el mantenimiento va incluido."

    monkeypatch.setattr(env.wai, "complete", fake_complete)
    async with env.Session() as db:
        r = await env.agent.process_customer_message("el mantenimiento y soporte posterior, ¿cómo es?", db)
    assert r.source == "llm" and not r.needs_ticket
    assert "mantenimiento va incluido" in seen["system"]          # la entrada relevante viaja
    assert "videollamada corta" not in seen["system"]             # las irrelevantes no
    assert seen["model"] == env.settings.cf_response_model
    snap = env.usage.snapshot()
    assert snap["llm_calls"] == 1 and snap["est_tokens_saved_by_rag"] > 0


async def test_sin_cuota_diaria_cae_a_ticket_humano(env, monkeypatch):
    async def boom(*a, **k):
        raise env.wai.DailyLimitReached("agotada")

    monkeypatch.setattr(env.wai, "complete", boom)
    async with env.Session() as db:
        r = await env.agent.process_customer_message("¿integran con SAP y timbrado fiscal?", db)
    assert r.needs_ticket and r.source == "limit" and "persona del equipo" in r.response_text
    assert env.usage.snapshot()["limit_hits"] == 1


async def test_embeddings_encuentran_sinonimos_y_se_guardan(env, monkeypatch):
    env.settings.rag_embeddings = True
    calls = {"n": 0}

    def vec(text):  # "vector" de juguete: eje 0 = costo/precio, eje 1 = soporte/mantenimiento, eje 2 = resto
        t = text.lower()
        return [float("cuesta" in t or "$" in t or "precio" in t or "tarifa" in t),
                float("soporte" in t or "mantenimiento" in t or "ayuda" in t),
                0.1]

    async def fake_embed(texts, model=None):
        calls["n"] += 1
        return [vec(t) for t in texts]

    monkeypatch.setattr(env.wai, "embed", fake_embed)
    async with env.Session() as db:
        from sqlalchemy import select
        from backend.models import KnowledgeBase
        entries = (await db.execute(select(KnowledgeBase))).scalars().all()
        top = await env.rag.retrieve(db, "¿cuál es la tarifa?", entries, k=2)   # "tarifa" no aparece en ninguna entrada
        assert {e.question for e in top} == {"¿Cuánto cuesta una página web?", "¿Cuánto cuesta un sistema a medida?"}
        first_calls = calls["n"]
        await env.rag.retrieve(db, "¿cuál es la tarifa?", entries, k=2)
        assert calls["n"] == first_calls + 1                                      # solo embebe la pregunta; la KB ya está guardada
        assert all(e.embedding and json.loads(e.embedding) for e in entries)


async def test_si_fallan_los_embeddings_usa_lexico(env, monkeypatch):
    env.settings.rag_embeddings = True

    async def down(texts, model=None):
        raise env.wai.WorkersAIError("caído")

    monkeypatch.setattr(env.wai, "embed", down)
    async with env.Session() as db:
        from sqlalchemy import select
        from backend.models import KnowledgeBase
        entries = (await db.execute(select(KnowledgeBase))).scalars().all()
        top = await env.rag.retrieve(db, "recordatorios por whatsapp", entries, k=1)
    assert top[0].question == "¿Hacen recordatorios por WhatsApp?"


async def test_complete_y_error_3036(env, monkeypatch):
    class Resp:
        def __init__(self, status, body):
            self.status_code, self._b, self.is_success, self.text = status, body, status < 400, str(body)

        def json(self):
            return self._b

    class Client:
        queue = [Resp(200, {"success": True, "result": {"response": "hola"}}),
                 Resp(429, {"success": False, "errors": [{"code": 3036, "message": "limit"}]})]

        def __init__(self, *a, **k): ...
        async def __aenter__(self): return self
        async def __aexit__(self, *a): ...
        async def post(self, url, json=None, headers=None):
            assert "/accounts/acct/ai/run/" in url and headers["Authorization"] == "Bearer tok"
            return Client.queue.pop(0)

    monkeypatch.setattr(env.wai.httpx, "AsyncClient", Client)
    assert await env.wai.complete("sys", [{"role": "user", "content": "hi"}], "@cf/x") == "hola"
    with pytest.raises(env.wai.DailyLimitReached):
        await env.wai.complete("sys", [{"role": "user", "content": "hi"}], "@cf/x")


def test_migracion_agrega_columnas_a_bases_viejas(tmp_path, monkeypatch):
    db = tmp_path / "old.db"
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE knowledge_base (id INTEGER PRIMARY KEY, question TEXT, answer TEXT, category TEXT, times_used INTEGER, created_at DATETIME, updated_at DATETIME)")
    con.execute("CREATE TABLE leads (id INTEGER PRIMARY KEY, platform TEXT, sender_id TEXT, sender_name TEXT, first_message TEXT, status TEXT, notes TEXT, created_at DATETIME)")
    con.execute("CREATE TABLE customer_messages (id INTEGER PRIMARY KEY, platform TEXT, sender_id TEXT, sender_name TEXT, message TEXT, response TEXT, responded BOOLEAN, created_at DATETIME)")
    con.commit(); con.close()
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{db}")
    for m in [m for m in sys.modules if m == "main" or m.startswith("backend")]:
        del sys.modules[m]
    import asyncio
    database = importlib.import_module("backend.database")
    asyncio.run(database.init_db())
    con = sqlite3.connect(db)
    assert {"embedding", "embedding_hash"} <= {r[1] for r in con.execute("PRAGMA table_info(knowledge_base)")}
    assert {"intent", "followups_sent"} <= {r[1] for r in con.execute("PRAGMA table_info(leads)")}
    assert "direction" in {r[1] for r in con.execute("PRAGMA table_info(customer_messages)")}
