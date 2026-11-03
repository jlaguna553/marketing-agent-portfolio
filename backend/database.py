from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

from .config import get_settings

DATABASE_URL = get_settings().database_url

engine = create_async_engine(DATABASE_URL, echo=False)
AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


# Columnas agregadas después de la primera versión (SQLite no las crea con create_all en tablas existentes)
_NEW_COLUMNS = [
    ("knowledge_base", "embedding", "TEXT"),
    ("knowledge_base", "embedding_hash", "VARCHAR(40)"),
    ("leads", "intent", "VARCHAR(20) DEFAULT 'info'"),
    ("leads", "last_inbound_at", "DATETIME"),
    ("leads", "followups_sent", "INTEGER DEFAULT 0"),
    ("leads", "last_followup_at", "DATETIME"),
    ("customer_messages", "direction", "VARCHAR(5) DEFAULT 'in'"),
]


def _add_missing_columns(sync_conn):
    from sqlalchemy import text
    if sync_conn.dialect.name != "sqlite":
        return
    for table, column, ddl in _NEW_COLUMNS:
        cols = [r[1] for r in sync_conn.execute(text(f"PRAGMA table_info({table})"))]
        if cols and column not in cols:
            sync_conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}"))


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_add_missing_columns)


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session
