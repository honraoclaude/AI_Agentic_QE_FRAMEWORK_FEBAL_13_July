from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from .config import get_settings


class Base(DeclarativeBase):
    pass


engine = create_async_engine(get_settings().database_url, echo=False)
SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


# audit_events is append-only. Belt and braces: no update/delete endpoints,
# no ORM mutation paths, AND database triggers that reject UPDATE/DELETE.
AUDIT_APPEND_ONLY_TRIGGERS_SQLITE = [
    """
    CREATE TRIGGER IF NOT EXISTS audit_events_no_update
    BEFORE UPDATE ON audit_events
    BEGIN
        SELECT RAISE(ABORT, 'audit_events is append-only');
    END;
    """,
    """
    CREATE TRIGGER IF NOT EXISTS audit_events_no_delete
    BEFORE DELETE ON audit_events
    BEGIN
        SELECT RAISE(ABORT, 'audit_events is append-only');
    END;
    """,
]


async def create_schema(conn) -> None:
    """Create tables + append-only triggers. Shared by app startup and tests."""
    await conn.run_sync(Base.metadata.create_all)
    if conn.dialect.name == "sqlite":
        for ddl in AUDIT_APPEND_ONLY_TRIGGERS_SQLITE:
            await conn.execute(text(ddl))
    # Postgres equivalent (Step 5 / migration): a BEFORE UPDATE OR DELETE trigger
    # raising an exception; wired in via Alembic when the Postgres swap happens.


async def init_db() -> None:
    from . import models  # noqa: F401 — register all mappings

    async with engine.begin() as conn:
        await create_schema(conn)


async def get_session():
    async with SessionLocal() as session:
        yield session
