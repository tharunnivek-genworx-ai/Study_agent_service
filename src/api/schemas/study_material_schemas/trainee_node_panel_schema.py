# C:\CapStone\study_agent_service\src\api\schemas\study_material_schemas\trainee_node_panel_schema.py
"""
Response schemas for GET /trainee/nodes/{node_id}/panel.

The panel endpoint returns everything the right-hand detail view needs in one
round trip so the frontend does not compute progress, previews, or navigation
hints locally. Field names mirror the TypeScript types in
``frontend/src/features/trainee_study_material/types/traineeNodePanel.types.ts``.
"""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

NodePanelType = Literal["pure-parent", "mixed-parent", "leaf-available", "leaf-locked"]
SubtopicBadgeKind = Literal["available", "in_progress", "completed", "locked"]
QuizBadgeKind = Literal["none", "not_taken", "in_progress", "completed"]
QuizButtonVariant = Literal["primary", "secondary"]
MixedParentTab = Literal["study", "subtopics"]


class BreadcrumbItemOut(BaseModel):
    """One segment in the leaf-panel breadcrumb trail."""

    node_id: UUID
    title: str


class NavSuggestionOut(BaseModel):
    """Clickable sibling or next-up target (node_id + display title)."""

    node_id: UUID
    title: str
    label_prefix: str = "Next up"


class SubtopicPanelItemOut(BaseModel):
    """One row in the subtopic card list (Cases 1 and 2)."""

    node_id: UUID
    title: str
    is_published: bool
    lesson_count: int
    child_count: int
    meta_label: str
    badge_kind: SubtopicBadgeKind
    badge_label: str


class QuizPanelActionsOut(BaseModel):
    """Quiz CTA block for study-material panels — labels precomputed server-side."""

    show_quiz_button: bool = False
    quiz_id: UUID | None = None
    active_attempt_id: UUID | None = None
    can_start_new_attempt: bool = True
    quiz_button_label: str = "Take quiz ↗"
    quiz_button_variant: QuizButtonVariant = "secondary"
    show_attempts_button: bool = False
    attempts_button_label: str = "View attempts"


class StudyMaterialSummaryOut(BaseModel):
    """Preview block for nodes with published material (not the full body)."""

    content_preview: str
    read_time_minutes: int
    read_percent: int = Field(..., ge=0, le=100)
    is_fully_read: bool
    quiz_available: bool
    quiz_passed: bool
    quiz_badge_kind: QuizBadgeKind = "none"
    quiz_badge_label: str | None = None
    reading_button_label: str = "Start reading ↗"
    quiz_actions: QuizPanelActionsOut | None = None
    completion_status: Literal["not_started", "in_progress", "completed"]
    progress_percentage: int = Field(..., ge=0, le=100)


class OverallProgressOut(BaseModel):
    """Footer rollup across all learning units in the selected subtree."""

    completed_units: int
    total_units: int
    percentage: int = Field(..., ge=0, le=100)
    label: str


class TraineeNodePanelOut(BaseModel):
    """Top-level response for the trainee topic detail panel."""

    panel_type: NodePanelType
    title: str
    header_meta: str
    study_material: StudyMaterialSummaryOut | None = None
    subtopics: list[SubtopicPanelItemOut] = Field(default_factory=list)
    availability_summary: str | None = None
    children_progress_label: str | None = None
    breadcrumbs: list[BreadcrumbItemOut] = Field(default_factory=list)
    back_navigation: NavSuggestionOut | None = None
    sibling_suggestions: list[NavSuggestionOut] = Field(default_factory=list)
    next_up: NavSuggestionOut | None = None
    overall_progress: OverallProgressOut | None = None
    default_tab: MixedParentTab | None = None
    all_subtopics_locked: bool = False
    is_fully_complete: bool = False
