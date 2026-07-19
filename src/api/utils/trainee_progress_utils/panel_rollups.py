"""
Progress badge and rollup label helpers for the topic detail panel.

These translate progress snapshots into UI-facing strings. They belong in the
progress domain because they interpret ``completion_status`` and read
percentages — not study-material content.
"""

from src.api.schemas.progress_schemas import (
    TraineeNodeProgressBatchItemOut,
)


def build_subtopic_progress_badge(
    *,
    is_published: bool,
    access_status: str = "available",
    completed_units: int,
    total_units: int,
    progress: TraineeNodeProgressBatchItemOut | None,
    has_subtree_activity: bool = False,
    subtree_avg_percent: int = 0,
) -> tuple[str, str]:
    """Return ``(badge_kind, badge_label)`` for a subtopic card pill.

    Badge priority (highest to lowest):
      locked     → no accessible content
      completed  → all units fully done
      in_progress → partial progress at any depth
      available  → not started

    ``subtree_avg_percent`` is the weighted-average ``progress_percentage``
    across all published units in the subtopic's subtree (0–100).  It drives
    the badge label for intermediate nodes where the ``progress`` snapshot
    belongs to the subtopic node itself (which may have no direct material).
    """
    if access_status == "coming_soon" or not is_published:
        return "locked", "Coming soon"
    if access_status == "prerequisite_locked":
        return "prerequisite_locked", "Prerequisite"
    if total_units > 0 and completed_units >= total_units:
        return "completed", "Done ✓"
    # Any directly-known progress on the subtopic node itself
    if progress is not None and progress.completion_status == "in_progress":
        if total_units > 1:
            if completed_units > 0:
                return "in_progress", f"{completed_units} / {total_units} done"
            if subtree_avg_percent > 0:
                return "in_progress", f"{subtree_avg_percent}% done"
            return "in_progress", "In progress"
        # Single-unit subtopic: use progress_percentage for an accurate label
        if progress.progress_percentage > 0:
            return "in_progress", f"{progress.progress_percentage}% done"
        if progress.study_material_read_percent > 0:
            return "in_progress", f"{progress.study_material_read_percent}% read"
        return "in_progress", "In progress"
    # No direct progress but something is happening deeper in the subtree
    if has_subtree_activity or subtree_avg_percent > 0:
        if total_units > 1:
            if completed_units > 0:
                return "in_progress", f"{completed_units} / {total_units} done"
            if subtree_avg_percent > 0:
                return "in_progress", f"{subtree_avg_percent}% done"
        elif subtree_avg_percent > 0:
            return "in_progress", f"{subtree_avg_percent}% done"
        return "in_progress", "In progress"
    return "available", "Not started"


def build_children_progress_label(
    *,
    completed_available: int,
    available_count: int,
) -> str | None:
    """Optional line: "1 of 2 available subtopics completed"."""
    if available_count == 0:
        return None
    unit = "subtopic" if available_count == 1 else "subtopics"
    return f"{completed_available} of {available_count} available {unit} completed"


def build_overall_progress_label(
    *,
    completed_units: int,
    total_units: int,
    percentage: int,
) -> str:
    """Footer copy for mixed-parent and pure-parent overall progress block."""
    unit = "learning unit" if total_units == 1 else "learning units"
    return (
        f"{completed_units} of {total_units} {unit} complete across this topic · "
        f"{percentage}% overall"
    )
