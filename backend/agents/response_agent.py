"""
Agente especializado en atención a clientes de Doña Felix.
Toma pedidos, resuelve dudas usando la Base de Conocimiento (KB),
y cuando no puede responder crea un ticket de ayuda para el operador.

Flujo:
  1. Recibe mensaje del cliente
  2. Carga KB relevante de la DB
  3. Genera respuesta con el modelo IA
  4. Detecta si el modelo marcó que necesita ayuda ([TICKET])
  5. Retorna: texto para el cliente + flag de ticket + pregunta extraída
"""
import re
from dataclasses import dataclass
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from ..config import get_settings
from ..models import KnowledgeBase

settings = get_settings()

# Marcador que el modelo usa para señalar que necesita crear un ticket
_TICKET_MARKER = "[TICKET]"

CUSTOMER_SYSTEM_PROMPT_TEMPLATE = """Eres el asistente virtual de "{business_name}", una gordería artesanal.

Descripción: {business_description}

════════════════════════════════════════
CONOCIMIENTO DEL NEGOCIO (úsalo siempre):
{kb_content}
════════════════════════════════════════

TU ROL:
- Tomar pedidos: confirmar tipo de gordita, cantidad y nombre del cliente
- Responder dudas sobre el negocio usando SOLO el conocimiento de arriba
- Si te preguntan algo que NO está en tu conocimiento, crear un ticket de ayuda

REGLAS ESTRICTAS:
1. Responde en el mismo idioma que el cliente
2. Usa emojis con moderación (es una gordería tradicional, sé cálido y amable)
3. Al tomar un pedido, repite el resumen antes de confirmar
4. Si puedes responder con el conocimiento disponible, responde DIRECTAMENTE sin ningún formato especial
5. SOLO si la pregunta NO está cubierta en tu conocimiento, usa EXACTAMENTE este formato al final:

{ticket_marker}
PREGUNTA: [la pregunta específica del cliente, resumida en una línea]
RESPUESTA_CLIENTE: [mensaje amable al cliente, máximo 2 líneas, prometiendo respuesta rápida]

6. NUNCA uses el formato de ticket si ya respondiste la pregunta
7. NUNCA inventes precios, horarios ni información que no esté en tu conocimiento
8. Si el cliente está enojado, sé empático y ofrece escalar con el operador
"""


@dataclass
class AgentResult:
    """Resultado del procesamiento de un mensaje de cliente."""
    response_text: str        # Texto a enviar al cliente
    needs_ticket: bool        # ¿Se debe crear ticket?
    ticket_question: str      # Pregunta extraída para el ticket


async def _load_kb_content(db: AsyncSession) -> str:
    """Carga la base de conocimiento y la formatea para el prompt."""
    result = await db.execute(
        select(KnowledgeBase).order_by(KnowledgeBase.category, KnowledgeBase.id)
    )
    entries = result.scalars().all()

    if not entries:
        return "(La base de conocimiento está vacía. Usa tickets para ir llenándola.)"

    # Incrementar contador de uso
    sections: dict[str, list[str]] = {}
    for e in entries:
        cat = e.category.upper()
        sections.setdefault(cat, [])
        sections[cat].append(f"P: {e.question}\nR: {e.answer}")

    lines = []
    for cat, items in sections.items():
        lines.append(f"[{cat}]")
        lines.extend(items)
        lines.append("")
    return "\n".join(lines).strip()


def _build_system_prompt(kb_content: str) -> str:
    return CUSTOMER_SYSTEM_PROMPT_TEMPLATE.format(
        business_name=settings.business_name,
        business_description=settings.business_description,
        kb_content=kb_content,
        ticket_marker=_TICKET_MARKER,
    )


def _parse_response(raw: str) -> AgentResult:
    """
    Analiza el texto del modelo para detectar si pidió crear un ticket.
    Detección case-insensitive del marcador para compatibilidad con todos los modelos.
    """
    raw_lower = raw.lower()
    marker_lower = _TICKET_MARKER.lower()

    if marker_lower not in raw_lower:
        return AgentResult(response_text=raw.strip(), needs_ticket=False, ticket_question="")

    # Hay ticket marker: separar el texto previo del bloque de ticket
    marker_pos = raw_lower.find(marker_lower)
    text_before_marker = raw[:marker_pos].strip()

    # Extraer campos del bloque de ticket
    question_match = re.search(r"PREGUNTA:\s*(.+?)(?:\n|$)", raw, re.IGNORECASE)
    client_match = re.search(r"RESPUESTA_CLIENTE:\s*(.+?)$", raw, re.IGNORECASE | re.DOTALL)

    ticket_question = question_match.group(1).strip() if question_match else "Consulta del cliente"

    # Usar RESPUESTA_CLIENTE si existe, si no usar el texto antes del marcador
    if client_match:
        client_text = client_match.group(1).strip()
    elif text_before_marker:
        client_text = text_before_marker
    else:
        client_text = "Déjame consultar eso con el equipo y te respondo a la brevedad. 🙏"

    return AgentResult(
        response_text=client_text,
        needs_ticket=True,
        ticket_question=ticket_question,
    )


async def _anthropic_complete(system: str, messages: list[dict]) -> str:
    import anthropic
    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    response = await client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=600,
        system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
        messages=messages,
    )
    return response.content[0].text


async def _ollama_complete(system: str, messages: list[dict]) -> str:
    from ..ollama_client import complete
    return await complete(
        system=system,
        messages=messages,
        model=settings.ollama_response_model,
    )


async def process_customer_message(
    customer_message: str,
    db: AsyncSession,
    conversation_history: list[dict] | None = None,
    platform: str = "whatsapp",
) -> AgentResult:
    """
    Procesa un mensaje de cliente:
    - Carga KB de la DB
    - Genera respuesta con IA
    - Detecta si se necesita ticket de ayuda
    - Retorna AgentResult con todo lo necesario para el webhook
    """
    kb_content = await _load_kb_content(db)
    system = _build_system_prompt(kb_content)

    messages: list[dict] = []
    if conversation_history:
        for msg in conversation_history[-6:]:
            messages.append({"role": msg["role"], "content": msg["content"]})

    platform_hint = {
        "whatsapp": "[Cliente en WhatsApp — respuesta breve y cálida]",
        "facebook": "[Cliente en Facebook — puedes ser algo más detallado]",
    }.get(platform, "")

    messages.append({"role": "user", "content": customer_message + ("\n" + platform_hint if platform_hint else "")})

    if settings.llm_provider == "ollama":
        raw = await _ollama_complete(system, messages)
    else:
        raw = await _anthropic_complete(system, messages)

    return _parse_response(raw)


async def should_auto_respond(message: str) -> bool:
    """Filtra spam y mensajes que no ameritan respuesta."""
    message = message.strip()
    if len(message) < 2:
        return False
    spam_indicators = ["http://", "https://", "bit.ly", "www.", "promoción especial para ti"]
    return not any(s in message.lower() for s in spam_indicators)


# ── Compatibilidad con el webhook anterior ────────────────────
async def generate_customer_response(
    customer_message: str,
    conversation_history: list[dict] | None = None,
    platform: str = "whatsapp",
) -> str:
    """Wrapper simple sin DB — solo para casos donde no se necesita KB ni tickets."""
    if settings.llm_provider == "ollama":
        from ..ollama_client import complete
        from ..config import get_settings
        s = get_settings()
        system = _build_system_prompt("(Base de conocimiento no disponible en este contexto)")
        msgs = conversation_history[-4:] if conversation_history else []
        msgs.append({"role": "user", "content": customer_message})
        return await complete(system=system, messages=msgs, model=s.ollama_response_model)
    else:
        import anthropic
        client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
        system = _build_system_prompt("(Base de conocimiento no disponible en este contexto)")
        msgs = (conversation_history or [])[-4:] + [{"role": "user", "content": customer_message}]
        resp = await client.messages.create(
            model="claude-haiku-4-5-20251001", max_tokens=512,
            system=system, messages=msgs
        )
        return resp.content[0].text
