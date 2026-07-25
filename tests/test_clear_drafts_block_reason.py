"""Unit tests for clear-all-drafts block reasons when nothing is discardable."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

from src.api.core.services.study_agent_services.study_material_service import (
    _clear_drafts_block_reason_no_discardable_versions,
)


def _version(**kwargs: object) -> SimpleNamespace:
    defaults = {
        "lifecycle_status": "draft",
        "is_published": False,
        "is_archived": False,
        "published_at": None,
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def _published_at() -> datetime:
    return datetime(2026, 1, 1, tzinfo=UTC)


def test_previous_only_explains_history_kept_not_never_generated() -> None:
    versions = [
        _version(
            lifecycle_status="archived",
            is_published=False,
            published_at=_published_at(),
        )
    ]

    message = _clear_drafts_block_reason_no_discardable_versions(
        versions=versions,
        blocking_quiz_count=0,
    )

    assert "No study material has been generated" not in message
    assert "history" in message.lower()
    assert "Generate" in message


def test_empty_versions_still_says_never_generated() -> None:
    message = _clear_drafts_block_reason_no_discardable_versions(
        versions=[],
        blocking_quiz_count=0,
    )

    assert message == "No study material has been generated for this topic yet."


def test_live_only_still_asks_to_unpublish() -> None:
    versions = [
        _version(
            lifecycle_status="active",
            is_published=True,
            published_at=_published_at(),
        )
    ]

    message = _clear_drafts_block_reason_no_discardable_versions(
        versions=versions,
        blocking_quiz_count=0,
    )

    assert "live for trainees" in message
    assert "Unpublish" in message
