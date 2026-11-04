import asyncio
from types import SimpleNamespace as NS

from backend.agents import free_replies as fr
from backend.agents.free_replies import try_free_reply, similarity, normalize

KB = [
    NS(id=1, question="¿Cuánto cuesta una página web?", answer="Desde $1,000 MXN al mes."),
    NS(id=2, question="¿Qué es CaaS?", answer="Software a tu medida con renta mensual."),
]


def test_normalize_quita_acentos():
    assert normalize("¿Asesoría GRATIS?") == "asesoria gratis"


def test_saludo_sin_llm():
    r = try_free_reply("Hola buenas tardes", KB, has_history=False)
    assert r and r.reason == "greeting"


def test_saludo_con_historial_no_repite():
    assert try_free_reply("hola", KB, has_history=True) is None


def test_agenda_detectada():
    r = try_free_reply("Quiero agendar una cita", KB, has_history=False)
    assert r and r.reason == "booking" and r.wants_booking


def test_kb_coincide():
    r = try_free_reply("cuanto cuesta la pagina web", KB, has_history=False)
    assert r and r.reason == "kb" and r.kb_id == 1


def test_pregunta_desconocida_va_al_llm():
    assert try_free_reply("¿Integran con SAP?", KB, has_history=False) is None


def test_cache():
    fr.cache_put("¿Integran con SAP?", "Depende del caso.")
    r = try_free_reply("integran con sap", KB, has_history=False)
    assert r and r.reason == "cache"


def test_similitud_simetrica_basica():
    assert similarity("precio pagina web", "¿Cuánto cuesta una página web?") > 0.4


def test_singular_plural():
    kb = [NS(id=9, question="¿Hacen sistemas para escuelas?", answer="Sí.")]
    r = try_free_reply("tienen sistema para escuelas", kb, has_history=False)
    assert r and r.reason == "kb"
