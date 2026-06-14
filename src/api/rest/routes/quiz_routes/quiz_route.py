# src/api/rest/routes/quiz_route.py
"""
Routes for quizzes, quiz_questions, quiz_attempts, and quiz_question_responses.

Quiz lifecycle (TDD §3.2.2 and §3.2.3):
  MENTOR:
    Generate        → POST   /nodes/{node_id}/quizzes/generate      (LLM placeholder)
    List quizzes    → GET    /nodes/{node_id}/quizzes
    Get quiz        → GET    /nodes/{node_id}/quizzes/{quiz_id}
    Publish quiz    → PATCH  /nodes/{node_id}/quizzes/{quiz_id}/publish
    Add question    → POST   /nodes/{node_id}/quizzes/{quiz_id}/questions
    Update question → PATCH  /nodes/{node_id}/quizzes/{quiz_id}/questions/{question_id}
    Reorder qs      → PATCH  /nodes/{node_id}/quizzes/{quiz_id}/questions/reorder
    Delete question → DELETE /nodes/{node_id}/quizzes/{quiz_id}/questions/{question_id}

  TRAINEE:
    Start attempt   → POST   /nodes/{node_id}/quizzes/{quiz_id}/attempt
    Submit response → POST   /attempts/{attempt_id}/response
    Submit attempt  → POST   /attempts/{attempt_id}/submit
    Get attempt     → GET    /attempts/{attempt_id}
"""

from uuid import UUID

from fastapi import APIRouter, Depends, status
from fastapi.responses import PlainTextResponse
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.core.services.quiz_services.quiz_service import QuizService
from src.api.data.clients.postgres.database import get_db
from src.api.rest.routes.dependencies import get_current_user
from src.api.schemas.identity_schemas.auth_schema import TokenPayload
from src.api.schemas.quiz_schemas.quiz_schema import (
    QuizAttemptOut,
    QuizAttemptStartRequest,
    QuizAttemptSubmitRequest,
    QuizGenerateRequest,
    QuizListOut,
    QuizOut,
    QuizPublishRequest,
    QuizQuestionCreateRequest,
    QuizQuestionDeletedOut,
    QuizQuestionOut,
    QuizQuestionReorderRequest,
    QuizQuestionResponseOut,
    QuizQuestionResponseRequest,
    QuizQuestionUpdateRequest,
    TraineeQuizOut,
)

router = APIRouter(tags=["Quiz"])


# ── Mentor: Quiz Generation & Management ─────────────────────────────────────


@router.post(
    "/nodes/{node_id}/quizzes/generate",
    status_code=status.HTTP_202_ACCEPTED,
    response_class=PlainTextResponse,
)
async def generate_quiz(
    node_id: UUID,
    payload: QuizGenerateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: TokenPayload = Depends(get_current_user),
) -> str:
    """Mentor triggers quiz generation from a published study material version.

    All three hints per question are generated at this time — no LLM calls
    happen during trainee attempts (TDD §3.2.2).
    Returns a placeholder string until the Quiz Agent LLM pipeline is wired in.
    """
    service = QuizService(db)
    return await service.generate_quiz(
        node_id, payload, current_user.sub, current_user.role
    )


@router.get("/nodes/{node_id}/quizzes", response_model=QuizListOut)
async def list_quizzes(
    node_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: TokenPayload = Depends(get_current_user),
) -> QuizListOut:
    """Mentor lists all quiz generations for a node, newest first."""
    service = QuizService(db)
    return await service.list_quizzes(node_id, current_user.sub, current_user.role)


@router.get("/nodes/{node_id}/quizzes/{quiz_id}", response_model=QuizOut)
async def get_quiz(
    node_id: UUID,
    quiz_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: TokenPayload = Depends(get_current_user),
) -> QuizOut:
    """Mentor fetches a single quiz with all its questions."""
    service = QuizService(db)
    return await service.get_quiz(node_id, quiz_id, current_user.sub, current_user.role)


@router.patch(
    "/nodes/{node_id}/quizzes/{quiz_id}/publish",
    response_model=QuizOut,
)
async def publish_quiz(
    node_id: UUID,
    quiz_id: UUID,
    payload: QuizPublishRequest,
    db: AsyncSession = Depends(get_db),
    current_user: TokenPayload = Depends(get_current_user),
) -> QuizOut:
    """Mentor publishes a quiz, making it visible to trainees (is_published=True)."""
    service = QuizService(db)
    return await service.publish_quiz(
        node_id, quiz_id, payload, current_user.sub, current_user.role
    )


# ── Mentor: Question Management ───────────────────────────────────────────────


@router.post(
    "/nodes/{node_id}/quizzes/{quiz_id}/questions",
    response_model=QuizQuestionOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_quiz_question(
    node_id: UUID,
    quiz_id: UUID,
    payload: QuizQuestionCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: TokenPayload = Depends(get_current_user),
) -> QuizQuestionOut:
    """Mentor manually adds a question to an existing quiz.

    source is forced to 'mentor_manual' at the service layer.
    correct_option must reference a non-None option (validated in service).
    """
    service = QuizService(db)
    return await service.create_question(
        node_id, quiz_id, payload, current_user.sub, current_user.role
    )


@router.patch(
    "/nodes/{node_id}/quizzes/{quiz_id}/questions/{question_id}",
    response_model=QuizQuestionOut,
)
async def update_quiz_question(
    node_id: UUID,
    quiz_id: UUID,
    question_id: UUID,
    payload: QuizQuestionUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: TokenPayload = Depends(get_current_user),
) -> QuizQuestionOut:
    """Mentor partially updates a question. Triggers EC-12 notification if
    correct_option changes on a published quiz."""
    service = QuizService(db)
    return await service.update_question(
        node_id, quiz_id, question_id, payload, current_user.sub, current_user.role
    )


@router.patch(
    "/nodes/{node_id}/quizzes/{quiz_id}/questions/reorder",
    status_code=status.HTTP_200_OK,
)
async def reorder_quiz_questions(
    node_id: UUID,
    quiz_id: UUID,
    payload: QuizQuestionReorderRequest,
    db: AsyncSession = Depends(get_db),
    current_user: TokenPayload = Depends(get_current_user),
) -> dict[str, object]:
    """Bulk-update order_index for all active questions in a quiz.

    question_ids must be the complete active set — partial reorders are rejected.
    """
    service = QuizService(db)
    return await service.reorder_questions(
        node_id, quiz_id, payload, current_user.sub, current_user.role
    )


@router.delete(
    "/nodes/{node_id}/quizzes/{quiz_id}/questions/{question_id}",
    response_model=QuizQuestionDeletedOut,
)
async def delete_quiz_question(
    node_id: UUID,
    quiz_id: UUID,
    question_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: TokenPayload = Depends(get_current_user),
) -> QuizQuestionDeletedOut:
    """Mentor soft-deletes a question (is_active=False).

    Historical attempt responses for this question are preserved and rendered
    with '(Removed)' by the frontend (EC-10).
    """
    service = QuizService(db)
    return await service.delete_question(
        node_id, quiz_id, question_id, current_user.sub, current_user.role
    )


# ── Trainee: Attempt Lifecycle ────────────────────────────────────────────────


@router.post(
    "/nodes/{node_id}/quizzes/{quiz_id}/attempt",
    response_model=TraineeQuizOut,
    status_code=status.HTTP_201_CREATED,
)
async def start_quiz_attempt(
    node_id: UUID,
    quiz_id: UUID,
    payload: QuizAttemptStartRequest,
    db: AsyncSession = Depends(get_db),
    current_user: TokenPayload = Depends(get_current_user),
) -> TraineeQuizOut:
    """Trainee starts a new attempt on a published quiz.

    Creates a quiz_attempts row and returns the full question set with
    blank attempt state (EC-9: multiple attempts always allowed).
    """
    service = QuizService(db)
    return await service.start_attempt(
        node_id, quiz_id, payload, current_user.sub, current_user.role
    )


@router.post(
    "/attempts/{attempt_id}/response",
    response_model=QuizQuestionResponseOut,
)
async def submit_question_response(
    attempt_id: UUID,
    payload: QuizQuestionResponseRequest,
    db: AsyncSession = Depends(get_db),
    current_user: TokenPayload = Depends(get_current_user),
) -> QuizQuestionResponseOut:
    """Trainee submits or updates an answer for a question within an attempt.

    Wrong answer → hint_level_reached incremented, next hint revealed.
    Correct answer → was_locked=True; question cannot be changed (EC-7).
    was_skipped=True with no selected_option records a deliberate skip (EC-8).
    """
    service = QuizService(db)
    return await service.submit_response(
        attempt_id, payload, current_user.sub, current_user.role
    )


@router.post(
    "/attempts/{attempt_id}/submit",
    response_model=QuizAttemptOut,
)
async def submit_quiz_attempt(
    attempt_id: UUID,
    payload: QuizAttemptSubmitRequest,
    db: AsyncSession = Depends(get_db),
    current_user: TokenPayload = Depends(get_current_user),
) -> QuizAttemptOut:
    """Trainee submits the full attempt.

    Score is computed from existing quiz_question_responses rows.
    Engagement & Chat Service is notified separately to update
    trainee_node_progress (quiz_best_score, quiz_passed).
    """
    service = QuizService(db)
    return await service.submit_attempt(
        attempt_id, payload, current_user.sub, current_user.role
    )


@router.get("/attempts/{attempt_id}", response_model=TraineeQuizOut)
async def get_quiz_attempt(
    attempt_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: TokenPayload = Depends(get_current_user),
) -> TraineeQuizOut:
    """Trainee resumes a mid-progress attempt. Returns full question set with
    current attempt state merged in (EC-7 mid-quiz resume)."""
    service = QuizService(db)
    return await service.get_attempt(attempt_id, current_user.sub, current_user.role)
