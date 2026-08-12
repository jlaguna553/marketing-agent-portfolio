"""
Router del chat del dueño del negocio con el agente de marketing.
Soporta streaming de respuestas y ejecución de tools (crear/publicar posts).
"""
import json
from datetime import datetime
from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from ..database import get_db
from ..models import ChatMessage, Post
from ..agents.content_agent import chat_stream, generate_post_simple
from ..integrations.facebook import facebook_api
from ..config import get_settings

router = APIRouter(prefix="/api/chat", tags=["chat"])
settings = get_settings()


async def _handle_tool_call(tool_name: str, tool_input: dict, db: AsyncSession, ws: WebSocket):
    """Ejecuta una tool del agente y notifica al cliente vía WebSocket."""
    if tool_name == "create_post":
        content = tool_input.get("content", "")
        platform = tool_input.get("platform", "all")
        hashtags = tool_input.get("hashtags", [])
        publish_now = tool_input.get("publish_now", False)
        scheduled_time_str = tool_input.get("scheduled_time")

        full_content = content
        if hashtags:
            full_content += "\n\n" + " ".join(hashtags)

        post = Post(
            content=full_content,
            platform=platform,
            status="draft",
        )

        if publish_now:
            # Publicar inmediatamente
            try:
                if platform in ("facebook", "all"):
                    result = await facebook_api.publish_facebook_post(full_content)
                    post.external_id = result.get("id") or result.get("post_id")
                    post.status = "published"
                    post.published_at = datetime.utcnow()
                await ws.send_json({
                    "type": "tool_result",
                    "message": f"✅ Post publicado en {platform} exitosamente."
                })
            except Exception as e:
                post.status = "failed"
                post.error_message = str(e)
                await ws.send_json({
                    "type": "tool_result",
                    "message": f"⚠️ Post guardado pero falló la publicación: {e}"
                })
        elif scheduled_time_str:
            try:
                post.scheduled_at = datetime.fromisoformat(scheduled_time_str)
                post.status = "scheduled"
                await ws.send_json({
                    "type": "tool_result",
                    "message": f"📅 Post programado para {scheduled_time_str}"
                })
            except ValueError:
                post.status = "draft"
        else:
            await ws.send_json({
                "type": "tool_result",
                "message": "📝 Post guardado como borrador."
            })

        db.add(post)
        await db.commit()


@router.websocket("/ws")
async def chat_websocket(websocket: WebSocket, db: AsyncSession = Depends(get_db)):
    """
    WebSocket para el chat en tiempo real del dueño con el agente.
    Protocolo:
      - Cliente envía: {"message": "texto del usuario"}
      - Servidor envía stream: {"type": "delta", "text": "..."}
      - Servidor envía al terminar: {"type": "done"}
      - Servidor puede enviar: {"type": "tool_result", "message": "..."}
    """
    await websocket.accept()

    # Cargar historial de la sesión
    result = await db.execute(
        select(ChatMessage).order_by(ChatMessage.created_at.desc()).limit(20)
    )
    history_rows = list(reversed(result.scalars().all()))
    conversation: list[dict] = [
        {"role": row.role, "content": row.content} for row in history_rows
    ]

    try:
        while True:
            data = await websocket.receive_json()
            user_message = data.get("message", "").strip()
            if not user_message:
                continue

            # Guardar mensaje del usuario
            user_msg = ChatMessage(role="user", content=user_message)
            db.add(user_msg)
            await db.commit()

            conversation.append({"role": "user", "content": user_message})

            # Streaming de respuesta
            full_response = ""

            async def tool_callback(tool_name: str, tool_input: dict):
                await _handle_tool_call(tool_name, tool_input, db, websocket)

            async for chunk in chat_stream(conversation, tool_callback=tool_callback):
                full_response += chunk
                await websocket.send_json({"type": "delta", "text": chunk})

            await websocket.send_json({"type": "done"})

            # Guardar respuesta del asistente
            assistant_msg = ChatMessage(role="assistant", content=full_response)
            db.add(assistant_msg)
            await db.commit()

            conversation.append({"role": "assistant", "content": full_response})

    except WebSocketDisconnect:
        pass


@router.get("/history")
async def get_chat_history(limit: int = 50, db: AsyncSession = Depends(get_db)):
    """Obtiene el historial del chat."""
    result = await db.execute(
        select(ChatMessage).order_by(ChatMessage.created_at.desc()).limit(limit)
    )
    messages = list(reversed(result.scalars().all()))
    return [
        {
            "id": m.id,
            "role": m.role,
            "content": m.content,
            "created_at": m.created_at.isoformat()
        }
        for m in messages
    ]
