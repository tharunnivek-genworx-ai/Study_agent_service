"""Async SQLAlchemy engine and session utilities for the Study Agent Service."""

from collections.abc import AsyncGenerator

from sqlalchemy.engine import URL
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from src.api.config import settings


def build_database_url(drivername: str = "postgresql+asyncpg") -> URL:
    """Build a Postgres URL for TCP hosts or Cloud SQL Unix sockets."""
    if settings.database_hostname.startswith("/cloudsql/"):
        return URL.create(
            drivername=drivername,
            username=settings.database_username,
            password=settings.database_password,
            database=settings.database_name,
            query={"host": settings.database_hostname},
        )

    return URL.create(
        drivername=drivername,
        username=settings.database_username,
        password=settings.database_password,
        host=settings.database_hostname,
        port=int(settings.database_port),
        database=settings.database_name,
    )


SQLALCHEMY_DATABASE_URL = build_database_url()

engine = create_async_engine(
    SQLALCHEMY_DATABASE_URL,
    echo=settings.database_echo,
    # Cloud Run + managed Postgres can drop idle TCP connections.
    # Pre-ping and recycle help avoid reusing dead sockets.
    pool_pre_ping=True,
    pool_recycle=900,
    pool_timeout=30,
    connect_args={
        # Keep handshake bounded in constrained environments.
        "timeout": 20,
        # asyncpg statement cache can hold stale prepared statements
        # across aggressive connection churn.
        "statement_cache_size": 0,
    },
)


class Base(DeclarativeBase):
    pass


SessionLocal = async_sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
    class_=AsyncSession,
)


async def get_db() -> AsyncGenerator[AsyncSession]:
    """Yield a request-scoped session; commit on success, rollback on error."""
    from src.api.utils.generation_progress.advisory_lock import (
        prepare_session_for_generation,
        release_all_generation_locks,
    )

    async with SessionLocal() as session:
        await prepare_session_for_generation(session)
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await release_all_generation_locks(session)
