"""Server-side mentor quiz UI flag computation."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

if TYPE_CHECKING:
    from src.api.data.models.postgres.e_learning_content.quizzes import Quiz
    from src.api.schemas.quiz_schemas import QuizOut


class _PublishedVersionLike:
    version_id: UUID
    version_number: int
    generation_type: str
    content: str | None


def compute_mentor_quiz_ui_flags(
    *,
    published: _PublishedVersionLike | None,
    source_sm: _PublishedVersionLike | None = None,
    quiz_out: QuizOut | None = None,
    quiz_row: Quiz | None = None,
    hints_status: str | None = None,
    has_other_live_quiz: bool = False,
    live_sm_version_id: UUID | None = None,
    quiz_sm_version_label: str | None = None,
) -> dict[str, bool | str | None]:
    """Derive mentor quiz tab flags from published study material and quiz state.

    The nudge uses version-ID comparison rather than timestamps: the quiz's
    study_material_version_id is compared against the live SM version.  This
    means publishing an outdated quiz without regenerating it does NOT clear
    the nudge — the nudge persists until the quiz is regenerated from the
    current live SM.
    """
    resolved_source_sm = source_sm or published
    can_generate_quiz = bool(
        resolved_source_sm is not None and (resolved_source_sm.content or "").strip()
    )
    generate_disabled_tooltip: str | None = None
    if not can_generate_quiz:
        generate_disabled_tooltip = "Generate study material first."

    is_published = bool(
        (quiz_out and quiz_out.is_published) or (quiz_row and quiz_row.is_published)
    )
    total_questions = 0

    if quiz_out is not None:
        total_questions = quiz_out.total_questions
    elif quiz_row is not None:
        total_questions = quiz_row.total_questions

    has_quiz_questions = total_questions > 0
    has_quiz = quiz_out is not None or quiz_row is not None
    can_access_hints = has_quiz_questions

    hints_locked = is_published
    hints_locked_tooltip: str | None = None
    if hints_locked:
        hints_locked_tooltip = "Remove the quiz from students to edit hints"

    can_generate_hints = has_quiz_questions and not hints_locked
    can_regenerate_hints = can_generate_hints

    resolved_hints_status = hints_status
    if resolved_hints_status is None and quiz_out is not None:
        resolved_hints_status = quiz_out.hints_status

    can_publish_quiz = False
    publish_disabled_tooltip: str | None = None
    if not is_published:
        if published is None:
            publish_disabled_tooltip = (
                "Publish study material for trainees before publishing the quiz."
            )
        elif resolved_hints_status != "complete":
            publish_disabled_tooltip = "Generate hints for all questions first"
        else:
            can_publish_quiz = True

    # Empty drafts must remain editable so a mentor can add the first manual
    # question after a generation run returns no valid questions.
    can_edit_questions = has_quiz and not is_published
    can_regenerate_quiz = has_quiz_questions and not is_published

    # Soft nudge only — no blocking.  Show when the quiz's SM version ID
    # differs from the currently live SM version ID, regardless of publish
    # timestamps.  Publishing an outdated quiz without regenerating it will
    # NOT clear this flag.
    quiz_sm_version_id: UUID | None = None
    if quiz_out is not None and quiz_out.study_material_version_id:
        try:
            quiz_sm_version_id = UUID(str(quiz_out.study_material_version_id))
        except (ValueError, AttributeError):
            pass
    elif quiz_row is not None and quiz_row.study_material_version_id:
        quiz_sm_version_id = quiz_row.study_material_version_id

    show_update_quiz_nudge = bool(
        live_sm_version_id is not None
        and quiz_sm_version_id is not None
        and live_sm_version_id != quiz_sm_version_id
    )

    publish_quiz_button_label = (
        "Replace live quiz" if has_other_live_quiz else "Make quiz live for students"
    )
    unpublish_quiz_button_label = "Remove quiz from students"

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
            resolved_source_sm.version_id if resolved_source_sm else None
        ),
        "can_edit_questions": can_edit_questions,
        "can_regenerate_quiz": can_regenerate_quiz,
        "show_update_quiz_nudge": show_update_quiz_nudge,
        "quiz_sm_version_label": quiz_sm_version_label
        if show_update_quiz_nudge
        else None,
        "publish_quiz_button_label": publish_quiz_button_label,
        "unpublish_quiz_button_label": unpublish_quiz_button_label,
    }
