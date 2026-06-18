# C:\CapStone\study_agent_service\src\api\core\exceptions\progress_exceptions\progress_exceptions.py
"""
HTTP exceptions for trainee_node_progress and trainee_space_progress operations.

Edge cases covered (cross-referenced to TDD §3.6):
  EC-3   — Archived node: progress row preserved; node excluded from
            trainee_space_progress.total_nodes recomputation.
  EC-20  — New quiz published resets node completion: quiz_passed=False reset,
            completion_status='in_progress', node_completion_reset notification
            created. Handled by service; no exception raised for the reset itself.
  EC-21  — Study material completed but no quiz: study_material_completed=True,
            quiz_passed=False, completion_status='in_progress', progress=50%.
            No exception; this is a valid partial-progress state.
  EC-22  — Trainee passes then fails on later attempt: quiz_best_score=MAX(),
            quiz_passed stays TRUE once achieved. No exception; service enforces.
  EC-23  — Space progress mismatch: total_nodes recomputed on tree changes.
            No exception raised; recompute query runs at service layer.
  EC-28  — Soft-deleted trainee: all progress and attempts retained for audit;
            no exception raised for existing rows.
  EC-13  — Trainee removed from space: read-only access to past materials and
            attempt history. No new progress writes allowed.

Naming convention mirrors quiz_exceptions.py and auth_exceptions.py.
"""

from fastapi import HTTPException, status

# ── Not Found ─────────────────────────────────────────────────────────────────


class SpaceProgressNotFoundException(HTTPException):
    """
    Raised when no trainee_space_progress row exists for the given
    (trainee_id, space_id) pair. The row is created when a trainee
    joins a space; this exception fires if that row is missing unexpectedly.
    """

    def __init__(self) -> None:
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Space progress record not found.",
        )


class SpaceProgressRecomputeFailedException(HTTPException):
    """
    Raised when the trainee_space_progress recompute query cannot complete
    successfully for a given (trainee_id, space_id) pair.

    This is distinct from SpaceProgressNotFoundException: the space and
    trainee enrollment are valid, but the recompute itself failed — e.g.
    the underlying topic_nodes / study_material_versions join could not be
    evaluated consistently (concurrent tree mutation), or the recompute
    was triggered against a space with no active nodes to aggregate.

    EC-23: total_nodes/completed_nodes are recomputed on tree changes and
    publish/unpublish events. This exception guards that recompute step
    itself, not the read of an already-stored row.
    """

    def __init__(self) -> None:
        super().__init__(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Unable to recompute space progress at this time. "
                "Please retry; if the issue persists, the space's topic "
                "tree may be in an inconsistent state."
            ),
        )


# ── Access / Ownership ────────────────────────────────────────────────────────


class TraineeNotEnrolledInSpaceException(HTTPException):
    """
    Raised when the authenticated trainee is not an active member of
    the space referenced in the request (space_trainees.is_active=False
    or no row exists). Guards scroll-progress updates and attempt starts.

    EC-13: trainees removed from a space lose write access to new progress;
    historical data is preserved read-only at the service layer.
    """

    def __init__(self) -> None:
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "You are not an active member of this space and cannot "
                "update progress records."
            ),
        )


# ── Invalid State / Business Rule Violations ──────────────────────────────────


class ReadPercentOutOfRangeException(HTTPException):
    """
    Raised when the read_percent value in a PATCH /study-material/progress
    request falls outside the valid range [0, 100].
    Schema-level validation (Field ge=0, le=100) is the first line of defence;
    this exception provides a clear HTTP error if the value somehow bypasses it.
    """

    def __init__(self) -> None:
        super().__init__(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="read_percent must be between 0 and 100 inclusive.",
        )


class ReadPercentRegressionException(HTTPException):
    """
    Raised when a PATCH /study-material/progress request supplies a
    read_percent that is lower than the current stored value.

    Scroll progress is monotonically increasing — the frontend should only
    send updates when the trainee scrolls forward. Backwards progress
    (e.g., page refresh sending 0) must not overwrite a higher saved value.
    The service enforces this, but raises this exception if the payload
    explicitly tries to lower the value below the stored maximum.
    """

    def __init__(self) -> None:
        super().__init__(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "read_percent cannot be lower than the current saved value. "
                "Scroll progress is monotonically increasing."
            ),
        )


class StudyMaterialNotPublishedException(HTTPException):
    """
    Raised when a trainee attempts to update scroll progress for a node
    whose study material is not published (is_published=False on all
    study_material_versions for that node). Trainees can only interact
    with published content.
    """

    def __init__(self) -> None:
        super().__init__(
            status_code=status.HTTP_409_CONFLICT,
            detail="Study material for this node is not published.",
        )


class NodeNotActiveException(HTTPException):
    """
    Raised when a trainee attempts to update progress on a node that has
    been archived by the mentor (topic_nodes.is_active=False).

    EC-3: archived nodes still show historical progress read-only;
    new writes are blocked.
    """

    def __init__(self) -> None:
        super().__init__(
            status_code=status.HTTP_409_CONFLICT,
            detail="This topic node has been archived and no longer accepts progress updates.",
        )


class SpaceNotPublishedException(HTTPException):
    """
    Raised when a trainee tries to update progress in a space that has
    not been published by the mentor (e_spaces.is_published=False).
    Trainees cannot interact with unpublished spaces.
    """

    def __init__(self) -> None:
        super().__init__(
            status_code=status.HTTP_409_CONFLICT,
            detail="This space is not published and is not accessible to trainees.",
        )
