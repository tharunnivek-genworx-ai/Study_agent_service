# src/api/core/exceptions/quiz_exceptions/hint_generation_exceptions.py
"""
HTTP exceptions for hint generation on existing quiz questions.

Hint generation requires a persisted quiz with finalized questions.
It runs as a separate LangGraph flow from quiz question generation.
"""

from fastapi import HTTPException, status


class QuizHasNoQuestionsException(HTTPException):
    """
    Raised when hint generation is requested for a quiz that has no
    active questions. Hints cannot be generated without question rows.
    """

    def __init__(self) -> None:
        super().__init__(
            status_code=status.HTTP_409_CONFLICT,
            detail="Create quiz questions before generating hints.",
        )


class HintsAlreadyCompleteException(HTTPException):
    """
    Raised on full hint generation when every active question already has
    all three hints populated. Use the regenerate endpoint to overwrite.
    """

    def __init__(self) -> None:
        super().__init__(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Every question already has hints. Use Regenerate hints to replace "
                "hints for specific questions."
            ),
        )


class HintsCannotGenerateOnPublishedQuizException(HTTPException):
    """
    Raised when a mentor tries to generate or regenerate hints on a
    published quiz. Hint writes are restricted to unpublished drafts.
    """

    def __init__(self) -> None:
        super().__init__(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "You cannot change hints on a quiz that is already live for students. "
                "Create a new quiz draft first."
            ),
        )


class HintQuestionsNotFoundException(HTTPException):
    """
    Raised when one or more question_ids in a selective regeneration
    request do not exist, are inactive, or do not belong to the quiz.
    """

    def __init__(self) -> None:
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="One or more questions were not found for this quiz.",
        )


class HintsNothingToDeleteException(HTTPException):
    """Raised when delete hints is requested but no hints exist on the quiz."""

    def __init__(self) -> None:
        super().__init__(
            status_code=status.HTTP_409_CONFLICT,
            detail="This quiz has no generated hints to delete.",
        )


class HintsNothingToRegenerateException(HTTPException):
    """Raised when whole-quiz hint regeneration finds no complete hints."""

    def __init__(self) -> None:
        super().__init__(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "No active questions have complete hints to regenerate. "
                "Generate hints first."
            ),
        )


class HintGenerationFailedException(HTTPException):
    """
    Raised when the Hint Agent LLM call fails after maximum retry attempts
    (exponential backoff, max 3 retries per TDD §3.7 Reliability).
    """

    def __init__(
        self, message: str = "Hint generation failed. Please try again."
    ) -> None:
        super().__init__(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=message,
        )
