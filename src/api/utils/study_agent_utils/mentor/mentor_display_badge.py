"""Mentor-facing badges and visibility hints for study material versions."""

from __future__ import annotations

from datetime import datetime

from src.api.utils.content_lifecycle.constants import LIFECYCLE_ARCHIVED


def compute_mentor_display_badge(
    *,
    is_published: bool,
    lifecycle_status: str,
    is_archived: bool,
    published_at: datetime | None,
) -> str:
    """Return a single badge label for version history (priority order)."""
    if is_published:
        return "Live for students"
    if lifecycle_status == LIFECYCLE_ARCHIVED:
        return "Previous for students"
    if is_archived:
        return "In your archive"
    if published_at is not None:
        return "Removed from students"
    return "Your draft"


def compute_student_visibility_hint(
    *,
    is_published: bool,
    lifecycle_status: str,
    is_archived: bool,
    published_at: datetime | None,
    is_viewing: bool,
) -> str | None:
    """One-line hint shown under the selected version in history."""
    if not is_viewing:
        return None
    if is_published:
        return "Students currently see this version as the live study material."
    if lifecycle_status == LIFECYCLE_ARCHIVED:
        return "Students can read this version in Previous versions."
    if is_archived:
        return "Students do not see archived drafts."
    if published_at is not None:
        return (
            "Students no longer see this version. "
            "It does not appear in Previous versions."
        )
    return "Students do not see unpublished drafts."
