from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("MOCK_INTEGRATIONS", "true")
    monkeypatch.setenv("DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path}/t.db")
    monkeypatch.setenv("KB_SEED_FILE", "data/kb_felix_software.json")
    monkeypatch.setenv("BOOKING_URL", "https://cal.example/felix")
    monkeypatch.setenv("OWNER_WHATSAPP", "5210000000000")
    import importlib, sys
    for m in [m for m in sys.modules if m == "main" or m.startswith("backend")]:
        del sys.modules[m]
    import main
    importlib.reload(main)
    with TestClient(main.app, base_url="http://localhost") as c:
        yield c


def sim(c, text, sender="5214610000001", channel="whatsapp"):
    r = c.post("/api/dev/simulate", json={"channel": channel, "sender_id": sender, "name": "Ana", "text": text})
    assert r.status_code == 200
    return c.get("/api/dev/outbox").json()


def test_flujo_agenda_crea_lead_responde_y_avisa(client):
    out = sim(client, "Quiero agendar una asesoría")
    texts = [o["content"] for o in out]
    assert any("https://cal.example/felix" in t for t in texts)          # respuesta con enlace de agenda
    assert any("Nuevo interesado" in t for t in texts)                   # aviso al dueño
    leads = client.get("/api/leads/").json()
    assert len(leads) == 1 and leads[0]["intent"] == "booking" and leads[0]["status"] == "new"


def test_duda_desconocida_crea_ticket(client):
    sim(client, "¿Integran con SAP y con timbrado fiscal?")
    tickets = client.get("/api/tickets/?status=open").json()
    assert len(tickets) == 1


def test_respuesta_manual_marca_contactado(client):
    sim(client, "Quiero agendar una cita")
    lead = client.get("/api/leads/").json()[0]
    r = client.post(f"/api/leads/{lead['id']}/reply", json={"text": "Hola Ana, ¿te late mañana a las 10?"})
    assert r.status_code == 200 and r.json()["status"] == "contacted"
    d = client.get(f"/api/leads/{lead['id']}").json()
    assert [t["from"] for t in d["thread"]][-1] == "owner"


def test_seguimiento_automatico_respeta_maximo(client):
    sim(client, "Quiero agendar una asesoria")
    assert client.post("/api/dev/run-followups?force=true").json()["sent"] == 1
    assert client.post("/api/dev/run-followups?force=true").json()["sent"] == 1
    assert client.post("/api/dev/run-followups?force=true").json()["sent"] == 0   # followup_max = 2


def test_no_hay_seguimiento_si_el_dueno_ya_respondio(client):
    sim(client, "Quiero agendar una asesoria")
    lead = client.get("/api/leads/").json()[0]
    client.post(f"/api/leads/{lead['id']}/reply", json={"text": "Hola, ¿mañana a las 10?"})
    assert client.post("/api/dev/run-followups?force=true").json()["sent"] == 0


def test_no_hay_seguimiento_si_ya_agendo(client):
    sim(client, "Quiero agendar una asesoria")
    lead = client.get("/api/leads/").json()[0]
    client.patch(f"/api/leads/{lead['id']}", json={"status": "scheduled"})
    assert client.post("/api/dev/run-followups?force=true").json()["sent"] == 0


def test_estado_invalido_rechazado(client):
    sim(client, "hola")
    lead = client.get("/api/leads/").json()[0]
    assert client.patch(f"/api/leads/{lead['id']}", json={"status": "xyz"}).status_code == 400


def test_panel_bloqueado_desde_fuera_pero_webhook_abierto(client):
    r = client.get("/api/leads/", headers={"host": "algo.ngrok-free.app"})
    assert r.status_code == 404
    r = client.get("/webhook/meta", headers={"host": "algo.ngrok-free.app"})
    assert r.status_code == 403   # llega al handler (token inválido), no lo bloquea el guardia
