import asyncio
import logging
from typing import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel, create_engine, Session

from src.config import settings

logger = logging.getLogger(__name__)


# Create async engine for PostgreSQL
engine = create_async_engine(
    settings.db_url,
    echo=True,  # Set to False in production
    future=True,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
)

# Async session factory
async_session_maker = sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency for getting async database sessions.
    
    Usage in FastAPI:
        @app.get("/items")
        async def get_items(session: AsyncSession = Depends(get_session)):
            ...
    """
    async with async_session_maker() as session:
        try:
            yield session
        finally:
            await session.close()


async def _init_db_once():
    async with engine.begin() as conn:
        # Import all models here to ensure they're registered
        from src.models import Shop, ShopSite, Customer, ChatEvent, Order

        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(SQLModel.metadata.create_all)


async def init_db() -> bool:
    """
    Initialize database tables.
    Returns True on success, False if it fails and strict mode is disabled.
    """
    retries = max(settings.db_init_retries, 1)
    delay = max(settings.db_init_delay_seconds, 0.1)
    backoff = max(settings.db_init_backoff, 1.0)
    last_exc = None

    for attempt in range(1, retries + 1):
        try:
            await _init_db_once()
            return True
        except Exception as exc:
            last_exc = exc
            logger.warning("DB init attempt %s/%s failed: %s", attempt, retries, exc)
            if attempt < retries:
                await asyncio.sleep(delay)
                delay *= backoff

    if settings.db_init_strict and last_exc:
        raise last_exc

    logger.error("DB init failed after %s attempts: %s", retries, last_exc)
    return False
