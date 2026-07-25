"""Unit tests for study-material lifecycle transitions."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

from src.api.utils.content_lifecycle.constants import (
    LIFECYCLE_ARCHIVED,
    LIFECYCLE_DRAFT,
)
from src.api.utils.content_lifecycle.transitions import (
    transition_sm_to_archived,
    transition_sm_to_hidden,
)


def _live_version(**kwargs: object) -> SimpleNamespace:
    defaults = {
        "is_published": True,
        "lifecycle_status": "active",
        "superseded_at": None,
        "is_active": True,
        "published_at": datetime(2026, 1, 1, tzinfo=UTC),
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def test_transition_sm_to_archived_clears_is_active() -> None:
    version = _live_version()

    transition_sm_to_archived(version)

    assert version.is_published is False
    assert version.lifecycle_status == LIFECYCLE_ARCHIVED
    assert version.superseded_at is not None
    assert version.is_active is False


def test_transition_sm_to_hidden_clears_is_active() -> None:
    version = _live_version()

    transition_sm_to_hidden(version)

    assert version.is_published is False
    assert version.lifecycle_status == LIFECYCLE_DRAFT
    assert version.superseded_at is None
    assert version.is_active is False
