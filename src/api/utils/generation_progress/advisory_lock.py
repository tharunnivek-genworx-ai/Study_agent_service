"""PostgreSQL advisory locks for generation pipeline concurrency."""

from __future__ import annotations

import hashlib
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.core.exceptions import (
    GenerationAdvisoryLockUnavailableException,
)

_LOCKS_INFO_KEY = "generation_advisory_locks"


def _lock_token(pipeline: str, resource_id: UUID) -> tuple[str, str]:
    return pipeline, str(resource_id)


def _tracked_locks(session: AsyncSession) -> set[tuple[str, str]]:
    locks = session.info.get(_LOCKS_INFO_KEY)
    if not isinstance(locks, set):
        locks = set()
        session.info[_LOCKS_INFO_KEY] = locks
    return locks


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
    """Try to acquire a session-scoped advisory lock for a generation resource.

      Session-level locks survive intermediate transaction commits (e.g. LangGraph
      checkpoint durability) and are released via ``release_generation_lock`` or
      ``release_all_generation_locks`` before the connection returns to the pool.

    Re-entrant acquires for the same pipeline/resource on one session are tracked
    in ``session.info`` so nested generation steps do not trip over each other or
    emit PostgreSQL unlock warnings on release.
    """
    token = _lock_token(pipeline, resource_id)
    if token in _tracked_locks(session):
        return True

    key1, key2 = _lock_keys(pipeline, resource_id)
    result = await session.execute(
        text("SELECT pg_try_advisory_lock(:k1, :k2)"),
        {"k1": key1, "k2": key2},
    )
    acquired = bool(result.scalar())
    if acquired:
        _tracked_locks(session).add(token)
    return acquired


async def release_generation_lock(
    session: AsyncSession,
    *,
    pipeline: str,
    resource_id: UUID,
) -> bool:
    """Release one session-level advisory lock level for a generation resource."""
    token = _lock_token(pipeline, resource_id)
    locks = _tracked_locks(session)
    if token not in locks:
        return False

    key1, key2 = _lock_keys(pipeline, resource_id)
    result = await session.execute(
        text("SELECT pg_advisory_unlock(:k1, :k2)"),
        {"k1": key1, "k2": key2},
    )
    released = bool(result.scalar())
    if released:
        locks.discard(token)
    return released


async def release_all_generation_locks(session: AsyncSession) -> None:
    """Release every session-level advisory lock held by this connection."""
    locks = session.info.pop(_LOCKS_INFO_KEY, None)
    if not locks:
        return
    await session.execute(text("SELECT pg_advisory_unlock_all()"))


async def require_generation_lock(
    session: AsyncSession,
    *,
    pipeline: str,
    resource_id: UUID,
) -> None:
    """Acquire lock or raise 409 if another session holds it."""
    if not await try_acquire_generation_lock(
        session, pipeline=pipeline, resource_id=resource_id
    ):
        raise GenerationAdvisoryLockUnavailableException()
