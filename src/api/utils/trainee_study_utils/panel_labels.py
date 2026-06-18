"""
Study-panel label helpers (non-progress).

Copy that depends only on tree/publish structure — not on trainee progress rows.
"""


def build_subtopic_meta_label(
    *,
    is_published: bool,
    lesson_count: int,
    child_count: int,
) -> str:
    """Secondary line under each subtopic title (e.g. "3 lessons")."""
    if not is_published:
        return "Coming soon"
    if lesson_count == 1:
        return "1 lesson"
    if lesson_count > 1:
        return f"{lesson_count} lessons"
    if child_count > 0:
        label = "subtopic" if child_count == 1 else "subtopics"
        return f"{child_count} {label}"
    return "Available"


def build_availability_summary(
    *,
    available_count: int,
    locked_count: int,
) -> str:
    """Muted one-liner under pure-parent headings."""
    total = available_count + locked_count
    if locked_count == 0:
        return f"{available_count} of {total} subtopics available"
    return (
        f"{available_count} of {total} subtopics available · {locked_count} coming soon"
    )


def default_mixed_parent_tab(
    *,
    study_material_completed: bool,
) -> str:
    """Default segmented-control tab for mixed-parent panels."""
    return "subtopics" if study_material_completed else "study"
