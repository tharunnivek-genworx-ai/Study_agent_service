"""Trainee and mentor progress tracking schemas."""

from src.api.schemas.progress_schemas.mentor_progress_schema import (
    MentorSpaceProgressOut,
    MentorSpaceProgressSummaryOut,
    NodeDeleteContentCascadeRequest,
    NodeDeletePreviewOut,
    NodeDeletePreviewRequest,
)
from src.api.schemas.progress_schemas.trainee_progress_schema import (
    CompletionStatus,
    TraineeNodeProgressBatchItemOut,
    TraineeNodeProgressBatchOut,
    TraineeNodeProgressBatchRequest,
    TraineeNodeProgressOut,
    TraineeNodeProgressSummaryOut,
    TraineeOwnSpaceProgressOut,
    TraineeProgressUpdateRequest,
    TraineeSpaceSummaryOut,
)

__all__ = [
    "CompletionStatus",
    "MentorSpaceProgressOut",
    "MentorSpaceProgressSummaryOut",
    "NodeDeleteContentCascadeRequest",
    "NodeDeletePreviewOut",
    "NodeDeletePreviewRequest",
    "TraineeNodeProgressBatchItemOut",
    "TraineeNodeProgressBatchOut",
    "TraineeNodeProgressBatchRequest",
    "TraineeNodeProgressOut",
    "TraineeNodeProgressSummaryOut",
    "TraineeOwnSpaceProgressOut",
    "TraineeProgressUpdateRequest",
    "TraineeSpaceSummaryOut",
]
