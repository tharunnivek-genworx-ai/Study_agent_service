"""HTTP exceptions for generation run lifecycle and resume."""

from datetime import datetime

from fastapi import HTTPException, status


class GenerationRunAborted(Exception):
    """Raised when a background job should stop (run cancelled or no longer active)."""


class GenerationRunNotFoundException(HTTPException):
    def __init__(self) -> None:
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Generation run not found.",
        )


class GenerationRunNotResumableException(HTTPException):
    def __init__(self, detail: str = "This generation run cannot be resumed.") -> None:
        super().__init__(
            status_code=status.HTTP_409_CONFLICT,
            detail=detail,
        )


class GenerationRunConflictException(HTTPException):
    """Raised when another run is already active for the same resource."""

    def __init__(self, run_id: str | None = None) -> None:
        detail = "A generation run is already in progress for this resource."
        if run_id:
            detail = f"{detail} Active run_id: {run_id}."
        super().__init__(
            status_code=status.HTTP_409_CONFLICT,
            detail=detail,
        )


class GenerationResumeTooEarlyException(HTTPException):
    def __init__(self, retry_after: datetime) -> None:
        super().__init__(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                "Resume is not available yet. Wait until the LLM retry cooldown expires."
            ),
            headers={"Retry-After": str(int(retry_after.timestamp()))},
        )


class GenerationAdvisoryLockUnavailableException(HTTPException):
    def __init__(self) -> None:
        super().__init__(
            status_code=status.HTTP_409_CONFLICT,
            detail="Could not acquire generation lock for this resource.",
        )


class GenerationPipelineResumeNotImplementedException(HTTPException):
    """Raised when resume is valid but the pipeline executor is not wired yet."""

    def __init__(self, pipeline: str) -> None:
        super().__init__(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail=(
                f"Resume execution for pipeline '{pipeline}' is not available yet."
            ),
        )


class GenerationRunNotCancellableException(HTTPException):
    """Raised when a generation run cannot be cancelled in its current status."""

    def __init__(
        self,
        detail: str = "This generation run cannot be cancelled.",
    ) -> None:
        super().__init__(
            status_code=status.HTTP_409_CONFLICT,
            detail=detail,
        )
