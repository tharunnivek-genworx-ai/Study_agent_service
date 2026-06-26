"""Unit tests for study-material visibility predicates."""

from __future__ import annotations

from types import SimpleNamespace

from src.api.utils.content_lifecycle.visibility import (
    is_mentor_discardable_sm,
    is_mentor_openable_sm,
)


def _version(**kwargs: object) -> SimpleNamespace:
    defaults = {
        "lifecycle_status": "draft",
        "is_published": False,
        "is_archived": False,
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def test_orphan_active_unpublished_is_discardable_not_openable() -> None:
    version = _version(lifecycle_status="active", is_published=False, is_active=False)

    assert is_mentor_discardable_sm(version) is True
    assert is_mentor_openable_sm(version) is False


def test_live_active_is_neither_discardable_nor_counted_as_workspace_only() -> None:
    version = _version(lifecycle_status="active", is_published=True)

    assert is_mentor_discardable_sm(version) is False
    assert is_mentor_openable_sm(version) is True


def test_student_archive_row_is_not_openable() -> None:
    version = _version(lifecycle_status="archived", is_published=False)

    assert is_mentor_openable_sm(version) is False
    assert is_mentor_discardable_sm(version) is False


def test_workspace_draft_is_openable_and_discardable() -> None:
    version = _version(lifecycle_status="draft", is_published=False)

    assert is_mentor_openable_sm(version) is True
    assert is_mentor_discardable_sm(version) is True
