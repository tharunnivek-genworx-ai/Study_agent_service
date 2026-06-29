"""
Completion status and progress-percentage derivation.

Single source of truth for how ``trainee_node_progress`` rows are interpreted
in API responses. Both ``TraineeProgressService`` (writes/reads) and panel
rollup helpers import from here so rules stay consistent.

When no quiz is published for a node, finishing the study material alone counts
as fully complete (100%). After a mentor publishes a quiz, completion requires
both reading and a passing score (50% per component).
"""

from src.api.schemas.progress_schemas import CompletionStatus


def compute_progress_percentage(
    *,
    study_material_completed: bool,
    quiz_passed: bool,
    has_published_quiz: bool = True,
) -> int:
    """Derive the 0 / 50 / 100 progress integer from the two binary components."""
    if not has_published_quiz:
        return 100 if study_material_completed else 0
    return (50 if study_material_completed else 0) + (50 if quiz_passed else 0)


def compute_completion_status(
    *,
    study_material_completed: bool,
    quiz_passed: bool,
    study_material_read_percent: int,
    quiz_attempt_count: int,
    has_published_quiz: bool = True,
) -> CompletionStatus:
    """Derive ``completion_status`` for API responses.

    With a published quiz:
      ``completed``   — study material and quiz both satisfied.
      ``in_progress`` — partial activity on either component.
      ``not_started`` — no scroll progress and no quiz attempts.

    Without a published quiz:
      ``completed``   — study material fully read.
      ``in_progress`` — partial reading only.
      ``not_started`` — no reading activity.
    """
    if has_published_quiz:
        if study_material_completed and quiz_passed:
            return "completed"
    elif study_material_completed:
        return "completed"
    if study_material_read_percent > 0 or quiz_attempt_count > 0:
        return "in_progress"
    return "not_started"


def is_learning_unit_complete(
    *,
    study_material_completed: bool,
    quiz_passed: bool,
    study_material_read_percent: int,
    quiz_attempt_count: int,
    has_published_quiz: bool,
) -> bool:
    """True when a published learning unit meets all current completion requirements."""
    return (
        compute_completion_status(
            study_material_completed=study_material_completed,
            quiz_passed=quiz_passed,
            study_material_read_percent=study_material_read_percent,
            quiz_attempt_count=quiz_attempt_count,
            has_published_quiz=has_published_quiz,
        )
        == "completed"
    )
