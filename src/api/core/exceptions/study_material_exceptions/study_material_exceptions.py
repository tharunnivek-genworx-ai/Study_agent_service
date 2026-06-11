# src/api/core/exceptions/content_exceptions/quiz_exceptions.py
"""
HTTP exceptions for quiz, quiz_questions, quiz_attempts,
and quiz_question_responses operations.

Edge cases covered (cross-referenced to TDD §3.6):
  EC-7   — Mid-quiz resume: handled by service loading existing responses;
            no exception raised on resume itself.
  EC-8   — Skip and submit: service handles prompt logic; no dedicated exception.
  EC-9   — Multiple attempts: always allowed; no exception.
  EC-10  — Deleted questions in historical attempts: soft-delete only;
            no exception raised, frontend renders '(Removed)'.
  EC-11  — Regenerate entire quiz: new row; no exception for the action itself.
  EC-12  — Wrong answer key corrected: update + notification; no exception.
  EC-20  — New quiz resets node completion: handled by Engagement & Chat Service.

Naming convention mirrors auth_exceptions.py and node_exceptions.py from Service 1.
"""

from fastapi import HTTPException, status

# ── Quiz Not Found ────────────────────────────────────────────────────────────


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


# ── Quiz State Conflicts ──────────────────────────────────────────────────────


class QuizAlreadyPublishedException(HTTPException):
    """
    Raised when a mentor tries to publish a quiz that is already published.
    Guards against duplicate publish events creating spurious
    node_event_notifications (mirrors VersionAlreadyPublishedException).
    """

    def __init__(self) -> None:
        super().__init__(
            status_code=status.HTTP_409_CONFLICT,
            detail="Quiz is already published.",
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


class QuizHasNoPublishedStudyMaterialException(HTTPException):
    """
    Raised during quiz generation when the provided
    study_material_version_id is not published (is_published=False).
    The Quiz Agent requires a published version as its source context —
    generating from an unpublished draft is not permitted.
    """

    def __init__(self) -> None:
        super().__init__(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Quiz can only be generated from a published study material version. "
                "Publish the version first."
            ),
        )


# ── Attempt State ─────────────────────────────────────────────────────────────


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


# ── Question Response State ───────────────────────────────────────────────────


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
    Raised when a response submission sets was_skipped=True but also
    provides a selected_option. A skip must have no selected option.
    """

    def __init__(self) -> None:
        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A skipped question cannot have a selected option.",
        )


# ── Access / Ownership ────────────────────────────────────────────────────────


class QuizForbiddenException(HTTPException):
    """
    Raised when a mentor attempts to modify, publish, or delete a quiz
    for a node in a space they do not own
    (COALESCE(transferred_to_mentor_id, mentor_id) check at service layer).
    """

    def __init__(self) -> None:
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to modify this quiz.",
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


# ── Generation Preconditions ──────────────────────────────────────────────────


class QuizGenerationFailedException(HTTPException):
    """
    Raised when the Quiz Agent LLM call fails after maximum retry attempts
    (exponential backoff, max 3 retries per TDD §3.7 Reliability).
    Mirrors LLMGenerationFailedException from study_material_exceptions.py.
    """

    def __init__(self) -> None:
        super().__init__(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Quiz generation failed. Please try again.",
        )


class StudyMaterialVersionMismatchException(HTTPException):
    """
    Raised when the study_material_version_id provided for quiz generation
    does not belong to the node in the path parameter. Prevents a quiz from
    being anchored to a version from a different node.
    """

    def __init__(self) -> None:
        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Study material version does not belong to this node.",
        )
