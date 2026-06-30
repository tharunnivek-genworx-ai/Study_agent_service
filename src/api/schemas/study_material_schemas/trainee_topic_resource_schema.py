"""Trainee-facing topic resources — node_media and visible reference materials."""

from uuid import UUID

from pydantic import BaseModel, Field

from src.api.schemas.study_material_schemas.node_media_schema import NodeMediaType


class TraineeTopicResourceOut(BaseModel):
    """One mentor-attached topic resource with display labels and URLs resolved server-side."""

    media_id: UUID
    media_type: NodeMediaType
    type_label: str
    display_title: str
    subtitle: str | None = None
    view_action_label: str
    download_action_label: str | None = None
    view_url: str
    download_url: str | None = None
    download_filename: str | None = None
    mime_type: str | None = None
    is_downloadable: bool = False
    order_index: int


class TraineeTopicResourceListOut(BaseModel):
    """List of supplementary materials for a topic node."""

    node_id: UUID
    items: list[TraineeTopicResourceOut] = Field(default_factory=list)
    total: int
    section_title: str = "Topic resources"
    empty_message: str = "No supplementary materials for this topic."
