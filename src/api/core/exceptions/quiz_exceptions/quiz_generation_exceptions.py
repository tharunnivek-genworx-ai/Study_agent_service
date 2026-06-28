# src/api/core/exceptions/content_exceptions/quiz_exceptions.py
"""
HTTP exceptions for quiz, quiz_questions, quiz_attempts,
and quiz_question_responses operations.

Edge cases covered (cross-referenced to TDD §3.6):
  EC-7   — Mid-quiz resume: handled by service loading existing responses;
            no exception raised on resume itself.
            Hint reveal order: hint_1 (1st wrong) → hint_2 (2nd) → hint_3 (3rd).
            hint_3 is the most explicit hint but does NOT reveal the answer.
            correct answer and explanation are post-submit only.
  EC-8   — Skip and submit: service handles prompt logic; no dedicated exception.
  EC-9   — Multiple attempts: always allowed; no exception.
  EC-10  — Deleted questions in historical attempts: soft-delete only;
            no exception raised, frontend renders '(Removed)'.
  EC-11  — Regenerate entire quiz: new row; no exception for the action itself.
  EC-12  — Wrong answer key corrected: update only; no exception.
  EC-20  — New quiz resets node completion: handled by quiz_service +
            progress_resets (see EC-20 in progress_exceptions.py).

Hint generation exceptions live in hint_generation_exceptions.py.

Naming convention mirrors auth_exceptions.py and node_exceptions.py from Service 1.
"""

from fastapi import HTTPException, status


class AppException(HTTPException):
    def __init__(self, status_code: int, error_code: str, message: str) -> None:
        super().__init__(
            status_code=status_code,
            detail={"error_code": error_code, "message": message},
        )


# ── Quiz Not Found ────────────────────────────────────────────────────────────


class QuizQuestionNotFoundException(HTTPException):
    """
    Raised when a question_id does not exist, does not belong to
    the specified quiz, or is already soft-deleted (is_active=False).
    """

    def __init__(self) -> None:
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Quiz question not found.",
        )


# ── Quiz State Conflicts ──────────────────────────────────────────────────────


class QuizAlreadyPublishedException(HTTPException):
    """
    Raised when a mentor tries to publish a quiz that is already published.
    Guards against duplicate publish events (mirrors VersionAlreadyPublishedException).
    """

    def __init__(self) -> None:
        super().__init__(
            status_code=status.HTTP_409_CONFLICT,
            detail="Quiz is already published.",
        )


class QuizNotPublishedForUnpublishException(HTTPException):
    """Raised when a mentor tries to unpublish a quiz that is not published."""

    def __init__(self) -> None:
        super().__init__(
            status_code=status.HTTP_409_CONFLICT,
            detail="Quiz is not published.",
        )


class QuizCannotDiscardRetiredException(HTTPException):
    """Raised when a mentor tries to discard a quiz kept in Previous versions."""

    def __init__(self) -> None:
        super().__init__(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "This quiz is still in Previous versions for students, so it can't be deleted. "
                'Unpublish it again and choose "Remove from students" if you want to delete it.'
            ),
        )


class QuizHasNoPublishedStudyMaterialException(HTTPException):
    """Raised when a mentor quiz action requires live study material on the node."""

    def __init__(self) -> None:
        super().__init__(
            status_code=status.HTTP_409_CONFLICT,
            detail=("Publish study material for trainees before working on the quiz."),
        )


class QuizStudyMaterialNotCurrentPublishedException(HTTPException):
    """Raised when a trainee attempt targets a quiz not tied to the live SM edition."""

    def __init__(self) -> None:
        super().__init__(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "This quiz is not aligned with the study material students see now. "
                "Start from the current topic content."
            ),
        )


class QuizCannotPublishWithoutPublishedStudyMaterialException(HTTPException):
    """Raised when a mentor tries to publish a quiz with no live study material."""

    def __init__(self) -> None:
        super().__init__(
            status_code=status.HTTP_409_CONFLICT,
            detail=("Publish study material for trainees before publishing the quiz."),
        )


# ── Attempt State ─────────────────────────────────────────────────────────────


# ── Question Response State ───────────────────────────────────────────────────


# ── Access / Ownership ────────────────────────────────────────────────────────


# ── Generation Preconditions ──────────────────────────────────────────────────


class QuizGenerationFailedException(HTTPException):
    """
    Raised when the Quiz Agent LLM call fails after maximum retry attempts
    (exponential backoff, max 3 retries per TDD §3.7 Reliability).
    Mirrors LLMGenerationFailedException from study_material_exceptions.py.
    """

    def __init__(
        self, message: str = "Quiz generation failed. Please try again."
    ) -> None:
        super().__init__(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=message,
        )


class QuizHintsIncompleteException(AppException):
    def __init__(self):  # type: ignore[no-untyped-def]
        super().__init__(
            status_code=422,
            error_code="QUIZ_HINTS_INCOMPLETE",
            message=("Generate hints for every question before publishing the quiz."),
        )
