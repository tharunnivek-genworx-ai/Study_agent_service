# src/api/core/exceptions/quiz_exceptions/trainee_exceptions.py
"""
HTTP exceptions for trainee-side quiz attempt operations.
"""

from uuid import UUID

from fastapi import HTTPException, status


class QuizNotFoundException(HTTPException):
    """
    Raised when a quiz_id does not exist or does not belong to the
    requested node. Applies to all quiz read and write operations.
    """

    def __init__(self) -> None:
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Quiz not found.",
        )


class QuizNotPublishedException(HTTPException):
    """
    Raised when a trainee attempts to start an attempt on a quiz that
    has not been published by the mentor (is_published=False).
    """

    def __init__(self) -> None:
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This quiz is not published and cannot be attempted.",
        )


class QuizAttemptNotFoundException(HTTPException):
    """
    Raised when an attempt_id does not exist or does not belong to
    the requesting trainee. Applies to response submission and submit.
    """

    def __init__(self) -> None:
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Quiz attempt not found.",
        )


class AttemptForbiddenException(HTTPException):
    """
    Raised when a trainee tries to access or modify an attempt that
    belongs to a different trainee. attempt_id ownership is validated
    against the JWT sub on every attempt route.
    """

    def __init__(self) -> None:
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to access this attempt.",
        )


class AttemptAlreadySubmittedException(HTTPException):
    """
    Raised when a trainee tries to submit a response or re-submit an attempt
    that already has status='submitted'. Submitted attempts are immutable.
    """

    def __init__(self) -> None:
        super().__init__(
            status_code=status.HTTP_409_CONFLICT,
            detail="This attempt has already been submitted.",
        )


class AttemptAbandonedException(HTTPException):
    """
    Raised when a trainee tries to interact with an attempt that has
    status='abandoned'. Abandoned attempts cannot be resumed or submitted.
    A new attempt must be started.
    """

    def __init__(self) -> None:
        super().__init__(
            status_code=status.HTTP_409_CONFLICT,
            detail="This attempt has been abandoned and cannot be modified.",
        )


class QuestionAlreadyLockedException(HTTPException):
    """
    Raised when a trainee tries to change the answer for a question that
    is already was_locked=True (answered correctly). Locked questions
    cannot be modified — the correct answer is final (EC-7).
    """

    def __init__(self) -> None:
        super().__init__(
            status_code=status.HTTP_409_CONFLICT,
            detail="This question is locked. Correct answers cannot be changed.",
        )


class QuestionBelongsToAnotherAttemptException(HTTPException):
    """
    Raised when the question_id in a response submission does not belong
    to the quiz associated with the given attempt_id. Prevents cross-attempt
    data corruption.
    """

    def __init__(self) -> None:
        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Question does not belong to this attempt's quiz.",
        )


class InvalidSkipPayloadException(HTTPException):
    """
    Raised when a response submission uses was_skipped=True.
    Deferring a question is UI navigation only; skipped status is computed on submit.
    """

    def __init__(self, detail: str | None = None) -> None:
        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=detail
            or "Use in-quiz navigation to move on; skipped status is computed when the attempt is submitted.",
        )


class AttemptAlreadyInProgressException(HTTPException):
    """Raised when a trainee tries to start a new attempt while one is in progress."""

    def __init__(self, attempt_id: UUID) -> None:
        super().__init__(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error_code": "ATTEMPT_ALREADY_IN_PROGRESS",
                "message": "You already have an in-progress attempt. Resume it or submit it first.",
                "active_attempt_id": str(attempt_id),
            },
        )
