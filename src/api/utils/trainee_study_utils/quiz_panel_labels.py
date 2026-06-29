"""
Quiz badge and action-label helpers for the trainee topic detail panel.

Translates published-quiz discovery + progress into UI-facing copy so the
frontend renders panel fields without local business rules.
"""

from typing import Literal
from uuid import UUID

from src.api.schemas.quiz_schemas import PublishedQuizDiscoveryOut

QuizBadgeKind = Literal["none", "not_taken", "in_progress", "completed"]
QuizButtonVariant = Literal["primary", "secondary"]


def build_quiz_badge(
    *,
    quiz_available: bool,
    quiz_passed: bool,
    has_in_progress_attempt: bool,
) -> tuple[QuizBadgeKind, str | None]:
    """Return ``(badge_kind, badge_label)`` for the study-material progress row."""
    if not quiz_available:
        return "none", None
    if quiz_passed:
        return "completed", "Quiz completed"
    if has_in_progress_attempt:
        return "in_progress", "Quiz in progress"
    return "not_taken", "Quiz not taken"


def build_quiz_button_label(*, has_in_progress_attempt: bool) -> str:
    if has_in_progress_attempt:
        return "Continue quiz attempt ↗"
    return "Take quiz ↗"


def build_quiz_button_variant(*, has_in_progress_attempt: bool) -> QuizButtonVariant:
    return "primary" if has_in_progress_attempt else "secondary"


def build_attempts_button_label(*, submitted_attempt_count: int) -> str:
    if submitted_attempt_count == 1:
        return "View past attempt"
    if submitted_attempt_count > 1:
        return f"View past attempts ({submitted_attempt_count})"
    return "View attempts"


def build_reading_button_label(*, read_percent: int) -> str:
    if read_percent > 0:
        return "Continue reading ↗"
    return "Start reading ↗"


def build_quiz_panel_actions(
    discovery: PublishedQuizDiscoveryOut,
) -> dict | None:
    """Build ``QuizPanelActionsOut`` fields from published-quiz discovery."""
    if discovery.quiz_id is None:
        return None

    has_in_progress = discovery.has_in_progress_attempt
    show_quiz_button = (
        not discovery.is_review_only
        and (discovery.can_start_new_attempt or has_in_progress)
    ) or (discovery.is_review_only and has_in_progress)
    return {
        "show_quiz_button": show_quiz_button,
        "quiz_id": discovery.quiz_id,
        "active_attempt_id": discovery.active_attempt_id,
        "can_start_new_attempt": discovery.can_start_new_attempt,
        "quiz_button_label": build_quiz_button_label(
            has_in_progress_attempt=has_in_progress
        ),
        "quiz_button_variant": build_quiz_button_variant(
            has_in_progress_attempt=has_in_progress
        ),
        "show_attempts_button": discovery.can_view_previous_attempts,
        "attempts_button_label": build_attempts_button_label(
            submitted_attempt_count=discovery.submitted_attempt_count
        ),
        "review_notice": discovery.review_notice,
    }


def build_panel_back_navigation(
    breadcrumbs: list[tuple[UUID, str]],
) -> dict | None:
    """Return parent nav target for the panel back link, or ``None`` at root."""
    if len(breadcrumbs) < 2:
        return None
    parent_id, parent_title = breadcrumbs[-2]
    return {
        "node_id": parent_id,
        "title": parent_title,
        "label_prefix": "Back to",
    }
