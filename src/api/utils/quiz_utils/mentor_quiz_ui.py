"""Server-side mentor quiz UI flag computation."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from src.api.utils.study_agent_utils.version_labels import build_version_display_label

if TYPE_CHECKING:
    from src.api.data.models.postgres.e_learning_content.quizzes import Quiz
    from src.api.schemas.quiz_schemas.quiz_schema import QuizOut


class _PublishedVersionLike:
    version_id: UUID
    version_number: int
    generation_type: str
    content: str | None


def _tooltip_study_material_not_published(version_label: str) -> str:
    return f"Study material {version_label} is not published"


def compute_mentor_quiz_ui_flags(
    *,
    published: _PublishedVersionLike | None,
    quiz_out: QuizOut | None = None,
    quiz_row: Quiz | None = None,
    hints_status: str | None = None,
    linked_version_number: int | None = None,
    linked_generation_type: str | None = None,
) -> dict[str, bool | str | None]:
    """Derive mentor quiz tab flags from published study material and quiz state."""
    can_generate_quiz = bool(
        published is not None and (published.content or "").strip()
    )
    generate_disabled_tooltip: str | None = None
    if not can_generate_quiz:
        generate_disabled_tooltip = (
            "Publish study material for trainees before generating a quiz."
        )

    is_published = bool(
        (quiz_out and quiz_out.is_published) or (quiz_row and quiz_row.is_published)
    )
    total_questions = 0
    study_material_version_id: UUID | None = None

    if quiz_out is not None:
        total_questions = quiz_out.total_questions
        study_material_version_id = quiz_out.study_material_version_id
    elif quiz_row is not None:
        total_questions = quiz_row.total_questions
        study_material_version_id = quiz_row.study_material_version_id

    linked_version_label: str | None = None
    if linked_version_number is not None and linked_generation_type is not None:
        linked_version_label = build_version_display_label(
            linked_version_number, linked_generation_type
        )

    current_published_version_label: str | None = None
    if published is not None:
        current_published_version_label = build_version_display_label(
            published.version_number, published.generation_type
        )

    is_linked_version_published = False
    if published is not None and study_material_version_id is not None:
        is_linked_version_published = published.version_id == study_material_version_id

    is_stale_version = bool(
        study_material_version_id is not None and not is_linked_version_published
    )

    has_quiz_questions = total_questions > 0
    can_access_hints = has_quiz_questions

    hints_locked = is_published
    hints_locked_tooltip: str | None = None
    if hints_locked:
        hints_locked_tooltip = "Unpublish the quiz to edit hints"

    version_blocked = is_stale_version and linked_version_label is not None
    version_block_tooltip = (
        _tooltip_study_material_not_published(linked_version_label)
        if version_blocked
        else None
    )

    can_generate_hints = has_quiz_questions and not hints_locked and not version_blocked
    can_regenerate_hints = can_generate_hints

    resolved_hints_status = hints_status
    if resolved_hints_status is None and quiz_out is not None:
        resolved_hints_status = quiz_out.hints_status

    can_publish_quiz = False
    publish_disabled_tooltip: str | None = None
    if not is_published and study_material_version_id is not None:
        if version_blocked and linked_version_label:
            publish_disabled_tooltip = _tooltip_study_material_not_published(
                linked_version_label
            )
        elif published is None:
            publish_disabled_tooltip = (
                "Publish study material for trainees before publishing the quiz."
            )
        elif resolved_hints_status != "complete":
            publish_disabled_tooltip = "Generate hints for all questions first"
        else:
            can_publish_quiz = True

    can_edit_questions = has_quiz_questions and not is_published and not version_blocked
    can_regenerate_quiz = (
        has_quiz_questions and not is_published and not version_blocked
    )

    edit_question_disabled_tooltip = version_block_tooltip
    regenerate_quiz_disabled_tooltip = version_block_tooltip

    generate_new_quiz_cta_label: str | None = None
    if is_stale_version and current_published_version_label:
        generate_new_quiz_cta_label = (
            f"Generate New Quiz for {current_published_version_label.split(' ')[0]}"
        )

    stale_helper_text: str | None = None
    if is_stale_version and linked_version_label:
        if current_published_version_label:
            stale_helper_text = (
                f"Generated from {linked_version_label.split(' ')[0]} · "
                f"Current published version is "
                f"{current_published_version_label.split(' ')[0]}"
            )
        else:
            stale_helper_text = (
                f"Generated from {linked_version_label.split(' ')[0]} · "
                "No study material is currently published"
            )

    quiz_title_with_version: str | None = None
    if quiz_out is not None and linked_version_label:
        short_label = linked_version_label.split(" ")[0]
        quiz_title_with_version = f"{quiz_out.title} ({short_label}) — Quiz"
    elif quiz_row is not None and linked_version_label:
        short_label = linked_version_label.split(" ")[0]
        quiz_title_with_version = f"{quiz_row.title} ({short_label}) — Quiz"

    return {
        "can_generate_quiz": can_generate_quiz,
        "generate_disabled_tooltip": generate_disabled_tooltip,
        "can_access_hints": can_access_hints,
        "hints_locked": hints_locked,
        "hints_locked_tooltip": hints_locked_tooltip,
        "can_generate_hints": can_generate_hints,
        "can_regenerate_hints": can_regenerate_hints,
        "can_publish_quiz": can_publish_quiz,
        "publish_disabled_tooltip": publish_disabled_tooltip,
        "published_study_material_version_id": (  # type: ignore[dict-item]
            published.version_id if published else None
        ),
        "study_material_version_id": study_material_version_id,  # type: ignore[dict-item]
        "is_linked_version_published": is_linked_version_published,
        "is_stale_version": is_stale_version,
        "linked_version_label": linked_version_label,
        "current_published_version_label": current_published_version_label,
        "stale_helper_text": stale_helper_text,
        "generate_new_quiz_cta_label": generate_new_quiz_cta_label,
        "quiz_title_with_version": quiz_title_with_version,
        "can_edit_questions": can_edit_questions,
        "can_regenerate_quiz": can_regenerate_quiz,
        "edit_question_disabled_tooltip": edit_question_disabled_tooltip,
        "regenerate_quiz_disabled_tooltip": regenerate_quiz_disabled_tooltip,
    }
