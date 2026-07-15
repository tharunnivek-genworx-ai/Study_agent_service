"""Content lifecycle transitions and queries for study material and quizzes."""

from src.api.utils.content_lifecycle.attempt_freeze import (
    abandon_in_progress_attempts_for_quizzes,
)
from src.api.utils.content_lifecycle.constants import (
    LIFECYCLE_ACTIVE,
    LIFECYCLE_ARCHIVED,
    LIFECYCLE_DISCARDED,
    LIFECYCLE_DRAFT,
    LIFECYCLE_HIDDEN,
)
from src.api.utils.content_lifecycle.queries import (
    count_blocking_quizzes_for_clear_drafts,
    list_trainee_archive_quizzes,
    list_trainee_archive_sm,
)
from src.api.utils.content_lifecycle.transitions import (
    transition_quiz_to_active,
    transition_quiz_to_archived,
    transition_quiz_to_discarded,
    transition_quiz_to_hidden,
    transition_sm_to_active,
    transition_sm_to_archived,
    transition_sm_to_discarded,
    transition_sm_to_hidden,
)
from src.api.utils.content_lifecycle.visibility import (
    exclude_discarded,
    is_discarded,
    is_mentor_accessible_sm,
    is_mentor_discardable_sm,
    is_mentor_openable_sm,
    is_mentor_visible_sm,
    is_trainee_live,
    is_trainee_live_quiz,
    is_trainee_live_sm,
)

__all__ = [
    "LIFECYCLE_ACTIVE",
    "LIFECYCLE_ARCHIVED",
    "LIFECYCLE_DISCARDED",
    "LIFECYCLE_DRAFT",
    "LIFECYCLE_HIDDEN",
    "abandon_in_progress_attempts_for_quizzes",
    "count_blocking_quizzes_for_clear_drafts",
    "exclude_discarded",
    "is_discarded",
    "is_mentor_accessible_sm",
    "is_mentor_discardable_sm",
    "is_mentor_openable_sm",
    "is_mentor_visible_sm",
    "is_trainee_live",
    "is_trainee_live_quiz",
    "is_trainee_live_sm",
    "list_trainee_archive_quizzes",
    "list_trainee_archive_sm",
    "transition_quiz_to_active",
    "transition_quiz_to_archived",
    "transition_quiz_to_discarded",
    "transition_quiz_to_hidden",
    "transition_sm_to_active",
    "transition_sm_to_archived",
    "transition_sm_to_discarded",
    "transition_sm_to_hidden",
]
