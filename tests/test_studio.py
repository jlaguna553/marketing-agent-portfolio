import importlib
import io
import sys

import pytest
from PIL import Image


def png(w=300, h=200, color=(200, 30, 30)):
    b = io.BytesIO()
    Image.new("RGB", (w, h), color).save(b, "PNG")
    return b.getvalue()


@pytest.fixture()
async def client(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "media").mkdir()
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path}/s.db")
    monkeypatch.setenv("MOCK_INTEGRATIONS", "true")
    monkeypatch.setenv("STUDIO_WORKER_URL", "")
    for m in [m for m in sys.modules if m == "main" or m.startswith("backend")]:
        del sys.modules[m]
    from httpx import ASGITransport, AsyncClient
    mod = importlib.import_module("main")  # importa modelos y routers antes de crear tablas
    from backend.database import init_db
    await init_db()
    async with AsyncClient(transport=ASGITransport(app=mod.app), base_url="http://localhost") as c:
        c.studio = importlib.import_module("backend.studio")
        c.tmp = tmp_path
        yield c


async def gen(c, files=None, **extra):
    data = {"campaign": "Promo de punto de venta para fondas y restaurantes", **extra}
    return await c.post("/api/studio/generate", data=data, files=files or [])


async def test_genera_simulado_con_imagen_y_plantilla(client):
    r = await gen(client, files=[("images", ("a.png", png(), "image/png"))])
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["source"] == "simulated" and j["post"]["headline"]
    out = Image.open(client.tmp / j["image_url"])
    assert out.size == (1080, 1080)
    assert (await client.get("/" + j["image_url"])).status_code == 200


async def test_sin_imagen_usa_fondo_de_marca(client):
    j = (await gen(client)).json()
    assert Image.open(client.tmp / j["image_url"]).size == (1080, 1080)


async def test_rechaza_archivo_que_no_es_imagen_sin_gastar_cuota(client, monkeypatch):
    called = []

    async def spy(*a, **k):
        called.append(1)
        return {}

    monkeypatch.setattr(client.studio, "generate_copy", spy)
    r = await gen(client, files=[("images", ("x.png", b"<?php evil ?>", "image/png"))])
    assert r.status_code == 400 and r.json()["detail"]["code"] == "bad_image"
    assert not called


async def test_limites_de_imagenes_y_validaciones(client):
    many = [("images", (f"{i}.png", png(), "image/png")) for i in range(5)]
    assert (await gen(client, files=many)).status_code == 400
    assert (await gen(client, network="tiktok")).status_code == 400
    assert (await client.post("/api/studio/generate", data={"campaign": "corta"})).status_code == 422


async def test_render_edita_titular_y_rechaza_ids_peligrosos(client):
    j = (await gen(client)).json()
    r = await client.post("/api/studio/render", json={"id": j["id"], "headline": "Otro titular", "cta": "Escríbenos"})
    assert r.status_code == 200
    for bad in ["../../etc/passwd", "ZZZ", "a" * 15]:
        assert (await client.post("/api/studio/render", json={"id": bad, "headline": "x"})).status_code == 400


async def test_save_crea_borrador_o_programado(client):
    j = (await gen(client)).json()
    r = await client.post("/api/studio/save", json={"id": j["id"], "content": "Texto", "platform": "facebook"})
    assert r.json()["status"] == "draft"
    r = await client.post("/api/studio/save", json={"id": j["id"], "content": "Texto", "scheduled_at": "2030-01-01T10:00:00"})
    assert r.json()["status"] == "scheduled"
    posts = (await client.get("/api/posts/")).json()
    assert posts[0]["image_url"] == f"media/studio/{j['id']}.png"
    assert (await client.post("/api/studio/save", json={"id": "../x", "content": "t"})).status_code == 400


async def test_worker_http_errores_y_exito(client, monkeypatch):
    st = client.studio
    monkeypatch.setattr(st.settings, "studio_worker_url", "https://w.test")
    monkeypatch.setattr(st.settings, "studio_worker_key", "k")

    class R:
        def __init__(self, code, body):
            self.status_code, self._b = code, body
            self.headers = {"content-type": "application/json"}

        def json(self):
            return self._b

    seen = {}
    resp = {"r": R(200, {"post": {"facebook": "f", "instagram": "i", "headline": "h", "cta": "c", "hashtags": []}, "warnings": ["w"]})}

    class FakeClient:
        def __init__(self, **k): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def post(self, url, headers, json):
            seen.update(url=url, auth=headers["Authorization"], body=json)
            return resp["r"]

    monkeypatch.setattr(st.httpx, "AsyncClient", FakeClient)
    r = await gen(client, files=[("images", ("a.png", png(), "image/png"))])
    assert r.status_code == 200 and r.json()["warnings"] == ["w"]
    assert seen["url"] == "https://w.test/generate" and seen["auth"] == "Bearer k"
    assert "images" not in seen["body"] and len(seen["body"]["campaign"]) > 10  # las imágenes nunca viajan al Worker

    resp["r"] = R(429, {"error": "daily_limit"})
    r = await gen(client)
    assert r.status_code == 429 and r.json()["detail"]["code"] == "daily_limit"
    resp["r"] = R(401, {"error": "unauthorized"})
    assert (await gen(client)).status_code == 502
