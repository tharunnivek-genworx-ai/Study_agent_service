"""Shared helpers for generation graph resume routing and checkpoint hydration."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any
from uuid import UUID

RESUME_FLAG = "_is_resume"
LAST_COMPLETED_NODE_KEY = "_last_completed_node"


def coerce_uuid(value: Any) -> Any:
    if isinstance(value, UUID):
        return value
    if isinstance(value, str) and value:
        try:
            return UUID(value)
        except ValueError:
            return value
    return value


def coerce_uuid_list(value: Any) -> Any:
    if not isinstance(value, list):
        return value
    return [coerce_uuid(item) for item in value]


def coerce_datetime(value: Any) -> Any:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str) and value:
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return value
    return value


def is_resume_state(state: Mapping[str, Any]) -> bool:
    return bool(state.get(RESUME_FLAG))


def last_completed_node_from_state(state: Mapping[str, Any]) -> str | None:
    value = state.get(LAST_COMPLETED_NODE_KEY)
    return str(value) if value else None
