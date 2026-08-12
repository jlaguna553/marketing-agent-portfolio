from datetime import datetime
from sqlalchemy import String, Text, DateTime, Boolean, Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column
from .database import Base
import enum


class PostStatus(str, enum.Enum):
    draft = "draft"
    scheduled = "scheduled"
    published = "published"
    failed = "failed"


class Platform(str, enum.Enum):
    facebook = "facebook"
    instagram = "instagram"
    whatsapp = "whatsapp"
    all = "all"


class Post(Base):
    __tablename__ = "posts"

    id: Mapped[int] = mapped_column(primary_key=True)
    content: Mapped[str] = mapped_column(Text)
    image_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    platform: Mapped[str] = mapped_column(String(20), default="all")
    status: Mapped[str] = mapped_column(String(20), default="draft")
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    external_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    role: Mapped[str] = mapped_column(String(20))  # user | assistant
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class CustomerMessage(Base):
    __tablename__ = "customer_messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    platform: Mapped[str] = mapped_column(String(20))  # whatsapp | facebook
    sender_id: Mapped[str] = mapped_column(String(100))
    sender_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    message: Mapped[str] = mapped_column(Text)
    response: Mapped[str | None] = mapped_column(Text, nullable=True)
    responded: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class KnowledgeBase(Base):
    """Compendio de preguntas y respuestas del negocio.
    Se alimenta manualmente y automáticamente cuando el operador resuelve tickets."""
    __tablename__ = "knowledge_base"

    id: Mapped[int] = mapped_column(primary_key=True)
    question: Mapped[str] = mapped_column(Text)        # Pregunta de referencia
    answer: Mapped[str] = mapped_column(Text)          # Respuesta oficial
    category: Mapped[str] = mapped_column(String(50), default="general")  # menu|horarios|pedidos|general
    times_used: Mapped[int] = mapped_column(default=0) # Cuántas veces ayudó al agente
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class HelpTicket(Base):
    """Pregunta de cliente que el agente no pudo responder.
    El operador la ve en la UI, responde, y esa respuesta va al cliente y a la KB."""
    __tablename__ = "help_tickets"

    id: Mapped[int] = mapped_column(primary_key=True)
    platform: Mapped[str] = mapped_column(String(20))
    sender_id: Mapped[str] = mapped_column(String(100))
    sender_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    original_message: Mapped[str] = mapped_column(Text)   # Mensaje completo del cliente
    extracted_question: Mapped[str] = mapped_column(Text) # Pregunta puntual extraída por el agente
    status: Mapped[str] = mapped_column(String(20), default="open")  # open | answered | dismissed
    operator_answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    answer_sent: Mapped[bool] = mapped_column(Boolean, default=False)
    save_to_kb: Mapped[bool] = mapped_column(Boolean, default=True)  # Si guardar en KB al responder
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    answered_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
