"""In-memory Groq API key pool with health tracking for rotation."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum

from src.api.config import llm_settings


class KeyStatus(StrEnum):
    HEALTHY = "healthy"
    BLOCKED = "blocked"
    RATE_LIMITED = "rate_limited"


@dataclass
class KeyEntry:
    alias: str
    api_key: str
    status: KeyStatus = KeyStatus.HEALTHY
    rate_limited_until: datetime | None = None


@dataclass
class GroqKeyPool:
    """Thread-safe pool of Groq API keys with rotation and exhaustion tracking."""

    _entries: list[KeyEntry] = field(default_factory=list)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    _round_robin: int = 0

    def _refresh_expired_rate_limits(self) -> None:
        now = datetime.now(UTC)
        for entry in self._entries:
            if (
                entry.status == KeyStatus.RATE_LIMITED
                and entry.rate_limited_until is not None
                and entry.rate_limited_until <= now
            ):
                entry.status = KeyStatus.HEALTHY
                entry.rate_limited_until = None

    def _is_usable(self, entry: KeyEntry) -> bool:
        if entry.status == KeyStatus.BLOCKED:
            return False
        if entry.status == KeyStatus.RATE_LIMITED:
            if entry.rate_limited_until is None:
                return False
            return entry.rate_limited_until <= datetime.now(UTC)
        return entry.status == KeyStatus.HEALTHY

    async def acquire_healthy_key(self) -> tuple[str, str] | None:
        """Return ``(alias, api_key)`` for the next healthy key, or ``None``."""
        async with self._lock:
            self._refresh_expired_rate_limits()
            if not self._entries:
                return None

            count = len(self._entries)
            for offset in range(count):
                idx = (self._round_robin + offset) % count
                entry = self._entries[idx]
                if self._is_usable(entry):
                    self._round_robin = (idx + 1) % count
                    return entry.alias, entry.api_key
            return None

    async def mark_blocked(self, alias: str) -> None:
        async with self._lock:
            for entry in self._entries:
                if entry.alias == alias:
                    entry.status = KeyStatus.BLOCKED
                    entry.rate_limited_until = None
                    return

    async def mark_rate_limited(self, alias: str, until: datetime) -> None:
        async with self._lock:
            for entry in self._entries:
                if entry.alias == alias:
                    entry.status = KeyStatus.RATE_LIMITED
                    entry.rate_limited_until = until
                    return

    async def all_exhausted(self) -> bool:
        """True when no key can be acquired (all blocked or rate-limited)."""
        async with self._lock:
            self._refresh_expired_rate_limits()
            return not any(self._is_usable(entry) for entry in self._entries)

    async def earliest_rate_limit_retry_at(self) -> datetime | None:
        """Earliest ``rate_limited_until`` among rate-limited keys."""
        async with self._lock:
            self._refresh_expired_rate_limits()
            times = [
                entry.rate_limited_until
                for entry in self._entries
                if entry.status == KeyStatus.RATE_LIMITED
                and entry.rate_limited_until is not None
            ]
            return min(times) if times else None

    async def all_blocked(self) -> bool:
        async with self._lock:
            if not self._entries:
                return True
            return all(entry.status == KeyStatus.BLOCKED for entry in self._entries)


def _build_key_entries() -> list[KeyEntry]:
    return [
        KeyEntry(alias=f"key_{index}", api_key=api_key)
        for index, api_key in enumerate(llm_settings.groq_api_keys(), start=1)
    ]


_shared_pool: GroqKeyPool | None = None


def get_shared_key_pool() -> GroqKeyPool:
    """Module singleton key pool (rebuilt when empty and keys are configured)."""
    global _shared_pool
    if _shared_pool is None or not _shared_pool._entries:
        _shared_pool = GroqKeyPool(_entries=_build_key_entries())
    return _shared_pool


def reset_shared_key_pool_for_tests() -> None:
    """Reset singleton — for unit tests only."""
    global _shared_pool
    _shared_pool = None
