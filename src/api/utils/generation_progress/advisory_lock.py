"""PostgreSQL advisory locks for generation pipeline concurrency."""

from __future__ import annotations

import hashlib
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.core.exceptions.generation_run_exceptions import (
    GenerationAdvisoryLockUnavailableException,
)


def _lock_keys(pipeline: str, resource_id: UUID) -> tuple[int, int]:
    """Derive two stable int32 advisory-lock keys from pipeline + resource id.

    Uses SHA-256 so keys are identical across all worker processes regardless
    of PYTHONHASHSEED (Python's built-in hash() is randomised per-process and
    must NOT be used here).
    """
    combined = f"{pipeline}:{resource_id}".encode()
    digest = hashlib.sha256(combined).digest()
    key1 = int.from_bytes(digest[:4], "big") & 0x7FFFFFFF
    key2 = int.from_bytes(digest[4:8], "big") & 0x7FFFFFFF
    return key1, key2


async def try_acquire_generation_lock(
    session: AsyncSession,
    *,
    pipeline: str,
    resource_id: UUID,
) -> bool:
    """Try to acquire a transaction-scoped advisory lock for a generation resource."""
    key1, key2 = _lock_keys(pipeline, resource_id)
    result = await session.execute(
        text("SELECT pg_try_advisory_xact_lock(:k1, :k2)"),
        {"k1": key1, "k2": key2},
    )
    acquired = result.scalar()
    return bool(acquired)


async def require_generation_lock(
    session: AsyncSession,
    *,
    pipeline: str,
    resource_id: UUID,
) -> None:
    """Acquire lock or raise 409 if another transaction holds it."""
    if not await try_acquire_generation_lock(
        session, pipeline=pipeline, resource_id=resource_id
    ):
        raise GenerationAdvisoryLockUnavailableException()
