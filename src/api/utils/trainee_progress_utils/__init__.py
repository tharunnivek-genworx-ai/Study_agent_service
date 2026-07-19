"""Progress-domain helpers (completion rules, rollups, badges, unlocking)."""

from src.api.utils.trainee_progress_utils.completion import (
    compute_completion_status,
    compute_progress_percentage,
    is_learning_unit_complete,
    score_meets_pass_threshold,
)
from src.api.utils.trainee_progress_utils.unlocking import (
    AccessResult,
    AccessStatus,
    UnlockProgressContext,
    UnlockTreeContext,
    assert_trainee_node_unlocked,
    batch_grant_children_on_parent_completed,
    clear_unlocks_for_reparented_node,
    grant_unlocks_after_child_content_published,
    grant_unlocks_after_node_completed,
    grant_unlocks_for_completed_trainees_on_node,
    resolve_node_access,
    resolve_node_access_with_grant,
)

__all__ = [
    "AccessResult",
    "AccessStatus",
    "UnlockProgressContext",
    "UnlockTreeContext",
    "assert_trainee_node_unlocked",
    "batch_grant_children_on_parent_completed",
    "clear_unlocks_for_reparented_node",
    "compute_completion_status",
    "compute_progress_percentage",
    "grant_unlocks_after_child_content_published",
    "grant_unlocks_after_node_completed",
    "grant_unlocks_for_completed_trainees_on_node",
    "is_learning_unit_complete",
    "resolve_node_access",
    "resolve_node_access_with_grant",
    "score_meets_pass_threshold",
]
