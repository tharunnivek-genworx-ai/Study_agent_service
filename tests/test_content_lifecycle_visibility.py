"""Unit tests for study-material visibility predicates."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

from src.api.utils.content_lifecycle.visibility import (
    is_mentor_discardable_sm,
    is_mentor_openable_sm,
    is_removed_from_students_sm,
    is_trainee_previous_sm,
    is_workspace_draft_sm,
    node_has_live_sm,
    node_has_workspace_draft_sm,
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


def test_orphan_active_unpublished_is_discardable_not_openable() -> None:
    version = _version(lifecycle_status="active", is_published=False, is_active=False)

    assert is_mentor_discardable_sm(version) is True
    assert is_mentor_openable_sm(version) is False
    assert is_workspace_draft_sm(version) is True


def test_live_active_is_neither_discardable_nor_counted_as_workspace_only() -> None:
    version = _version(
        lifecycle_status="active", is_published=True, published_at=_published_at()
    )

    assert is_mentor_discardable_sm(version) is False
    assert is_mentor_openable_sm(version) is True
    assert is_workspace_draft_sm(version) is False
    assert is_trainee_previous_sm(version) is False
    assert is_removed_from_students_sm(version) is False


def test_student_archive_row_is_not_openable() -> None:
    version = _version(
        lifecycle_status="archived",
        is_published=False,
        published_at=_published_at(),
    )

    assert is_mentor_openable_sm(version) is False
    assert is_mentor_discardable_sm(version) is False
    assert is_trainee_previous_sm(version) is True
    assert is_workspace_draft_sm(version) is False
    assert is_removed_from_students_sm(version) is False


def test_workspace_draft_is_openable_and_discardable() -> None:
    version = _version(lifecycle_status="draft", is_published=False)

    assert is_mentor_openable_sm(version) is True
    assert is_mentor_discardable_sm(version) is True
    assert is_workspace_draft_sm(version) is True
    assert is_trainee_previous_sm(version) is False
    assert is_removed_from_students_sm(version) is False


def test_removed_from_students_is_history_for_layer_but_still_discardable() -> None:
    version = _version(
        lifecycle_status="hidden",
        is_published=False,
        published_at=_published_at(),
    )

    assert is_removed_from_students_sm(version) is True
    assert is_workspace_draft_sm(version) is False
    assert is_trainee_previous_sm(version) is False
    assert is_mentor_discardable_sm(version) is True


def test_mentor_shelf_is_neither_workspace_draft_nor_removed() -> None:
    version = _version(
        lifecycle_status="draft",
        is_archived=True,
        published_at=None,
    )

    assert is_workspace_draft_sm(version) is False
    assert is_removed_from_students_sm(version) is False
    assert is_trainee_previous_sm(version) is False


def test_node_has_live_and_workspace_draft_helpers() -> None:
    draft = _version(lifecycle_status="draft")
    previous = _version(lifecycle_status="archived", published_at=_published_at())
    live = _version(
        lifecycle_status="active",
        is_published=True,
        published_at=_published_at(),
    )

    assert node_has_workspace_draft_sm([previous, draft]) is True
    assert node_has_workspace_draft_sm([previous]) is False
    assert node_has_live_sm([previous, draft]) is False
    assert node_has_live_sm([previous, live]) is True
