"""Central visibility predicates for study material and quiz lifecycle."""

from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy import ColumnElement

from src.api.data.models.postgres.e_learning_content.quizzes import Quiz
from src.api.data.models.postgres.e_learning_content.study_material_versions import (
    StudyMaterialVersion,
)
from src.api.utils.content_lifecycle.constants import (
    LIFECYCLE_ACTIVE,
    LIFECYCLE_ARCHIVED,
    LIFECYCLE_DISCARDED,
    LIFECYCLE_DRAFT,
    LIFECYCLE_HIDDEN,
)


def is_discarded(*, lifecycle_status: str) -> bool:
    """True when content was discarded from the mentor workspace."""
    return lifecycle_status == LIFECYCLE_DISCARDED


def exclude_discarded(lifecycle_status_column: ColumnElement) -> ColumnElement:
    """SQLAlchemy filter excluding discarded lifecycle rows."""
    return lifecycle_status_column != LIFECYCLE_DISCARDED


def is_mentor_discardable_sm(version: StudyMaterialVersion) -> bool:
    """SM rows in the mentor workspace that clear-all-drafts may remove.

    Includes draft WIP and explicitly-unpublished (hidden) rows still shown in
    working history. Also clears orphaned ``active`` rows that lost their publish
    flag without a lifecycle transition. Excludes live published content,
    shelf-archived rows, and superseded trainee archive history (archived
    lifecycle).
    """
    if is_discarded(lifecycle_status=version.lifecycle_status):
        return False
    if version.is_archived:
        return False
    if is_trainee_live_sm(version):
        return False
    if version.lifecycle_status == LIFECYCLE_ACTIVE:
        return not version.is_published
    return version.lifecycle_status in (LIFECYCLE_DRAFT, LIFECYCLE_HIDDEN)


def is_mentor_openable_sm(version: StudyMaterialVersion) -> bool:
    """SM the mentor can open from Generate / Material workspace actions.

    Excludes superseded trainee-archive rows and orphaned ``active`` lifecycle
    rows that are no longer live or an active working draft.
    """
    if not is_mentor_accessible_sm(version):
        return False
    if is_trainee_live_sm(version):
        return True
    return version.lifecycle_status in (LIFECYCLE_DRAFT, LIFECYCLE_HIDDEN)


def is_mentor_accessible_sm(version: StudyMaterialVersion) -> bool:
    """SM the mentor can open on the Material tab (workspace or live published).

    Excludes discarded rows, shelf-archived drafts, and superseded trainee
    archive history (archived lifecycle).
    """
    if is_discarded(lifecycle_status=version.lifecycle_status):
        return False
    if version.is_archived:
        return False
    if version.lifecycle_status == LIFECYCLE_ARCHIVED:
        return False
    return version.lifecycle_status in (
        LIFECYCLE_DRAFT,
        LIFECYCLE_HIDDEN,
        LIFECYCLE_ACTIVE,
    )


def is_mentor_visible_sm(version: StudyMaterialVersion) -> bool:
    """True when a version appears in mentor version history (any layer).

    Includes workspace drafts, live content, student-archive rows, and shelf
    drafts. Only discarded rows are excluded.
    """
    return not is_discarded(lifecycle_status=version.lifecycle_status)


def is_trainee_live(*, lifecycle_status: str, is_published: bool) -> bool:
    """Live trainee layer: published active content."""
    return lifecycle_status == LIFECYCLE_ACTIVE and is_published


def is_trainee_live_sm(version: StudyMaterialVersion) -> bool:
    return is_trainee_live(
        lifecycle_status=version.lifecycle_status,
        is_published=version.is_published,
    )


def is_trainee_live_quiz(quiz: Quiz) -> bool:
    return is_trainee_live(
        lifecycle_status=quiz.lifecycle_status,
        is_published=quiz.is_published,
    )


def is_trainee_previous_sm(version: StudyMaterialVersion) -> bool:
    """Student previous history: superseded live material kept for trainees."""
    return bool(version.lifecycle_status == LIFECYCLE_ARCHIVED)


def is_removed_from_students_sm(version: StudyMaterialVersion) -> bool:
    """Unpublished-from-live row still shown as Removed (hybrid clearable trash).

    Not live, not Previous, not mentor shelf. Must have been published at least
    once (``published_at`` set) and sit in draft/hidden lifecycle.
    """
    if is_trainee_live_sm(version):
        return False
    if is_trainee_previous_sm(version):
        return False
    if version.is_archived:
        return False
    if version.published_at is None:
        return False
    return version.lifecycle_status in (LIFECYCLE_DRAFT, LIFECYCLE_HIDDEN)


def is_workspace_draft_sm(version: StudyMaterialVersion) -> bool:
    """Mentor workspace draft layer ("Your draft") — not live/history/shelf.

    Matches unpublished WIP in draft/hidden lifecycle, plus orphaned ``active``
    rows that lost their publish flag without ``published_at``.
    """
    if is_discarded(lifecycle_status=version.lifecycle_status):
        return False
    if version.is_archived:
        return False
    if is_trainee_previous_sm(version):
        return False
    if is_trainee_live_sm(version):
        return False
    if version.published_at is not None:
        return False
    if version.lifecycle_status in (LIFECYCLE_DRAFT, LIFECYCLE_HIDDEN):
        return True
    # Orphan active unpublished without a prior publish timestamp.
    return version.lifecycle_status == LIFECYCLE_ACTIVE and not version.is_published


def node_has_live_sm(versions: Iterable[StudyMaterialVersion]) -> bool:
    """True when any version in the iterable is live for students."""
    return any(is_trainee_live_sm(version) for version in versions)


def node_has_workspace_draft_sm(versions: Iterable[StudyMaterialVersion]) -> bool:
    """True when any version in the iterable is a workspace draft."""
    return any(is_workspace_draft_sm(version) for version in versions)
