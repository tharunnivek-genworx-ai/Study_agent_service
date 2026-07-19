"""Panel API contract tests for publication and prerequisite lock states."""

from uuid import uuid4

from src.api.schemas.study_material_schemas import (
    SubtopicPanelItemOut,
    TraineeNodePanelOut,
)
from src.api.utils.trainee_progress_utils.panel_rollups import (
    build_subtopic_progress_badge,
)


def test_panel_exposes_prerequisite_blocker_metadata() -> None:
    parent_id = uuid4()
    child_id = uuid4()
    item = SubtopicPanelItemOut(
        node_id=child_id,
        title="Advanced",
        is_published=True,
        access_status="prerequisite_locked",
        blocked_by_node_id=parent_id,
        blocked_by_title="Basics",
        unlock_message="Finish Basics first",
        lesson_count=1,
        child_count=0,
        meta_label="1 lesson",
        badge_kind="prerequisite_locked",
        badge_label="Prerequisite",
    )
    panel = TraineeNodePanelOut(
        panel_type="mixed-parent",
        title="Course",
        header_meta="Study material + 1 subtopic",
        access_status="available",
        subtopics=[item],
    )

    assert panel.subtopics[0].is_published is True
    assert panel.subtopics[0].access_status == "prerequisite_locked"
    assert panel.subtopics[0].unlock_message == "Finish Basics first"


def test_badge_priority_distinguishes_prerequisite_from_coming_soon() -> None:
    prerequisite = build_subtopic_progress_badge(
        is_published=True,
        access_status="prerequisite_locked",
        completed_units=0,
        total_units=1,
        progress=None,
    )
    publication = build_subtopic_progress_badge(
        is_published=False,
        access_status="coming_soon",
        completed_units=0,
        total_units=0,
        progress=None,
    )

    assert prerequisite == ("prerequisite_locked", "Prerequisite")
    assert publication == ("locked", "Coming soon")
