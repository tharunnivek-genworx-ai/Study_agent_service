# src/api/rest/routes/trainee_quiz_routes/trainee_quiz_routes.py
"""
Routes for trainee quiz attempt operations.

Study material routes (reading, PDF, panel, scroll progress) live in
``trainee_study_routes`` — this module is quiz-only.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.core.services import (
    TraineeQuizService,
)
from src.api.data.clients.postgres import get_db
from src.api.rest.routes.dependencies import get_current_user
from src.api.schemas.identity_schemas import TokenPayload
from src.api.schemas.quiz_schemas import (
    ArchivedQuizReviewOut,
    PublishedQuizDiscoveryOut,
    QuizAttemptOut,
    QuizAttemptStartRequest,
    QuizAttemptSubmitRequest,
    QuizQuestionResponseOut,
    QuizQuestionResponseRequest,
    TraineeArchivedQuizListOut,
    TraineeQuizAttemptListOut,
    TraineeQuizOut,
)

router = APIRouter(prefix="/trainee", tags=["Trainee Quiz"])


@router.get(
    "/nodes/{node_id}/quizzes/published",
    response_model=PublishedQuizDiscoveryOut,
)
async def get_published_quiz_state(
    node_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: TokenPayload = Depends(get_current_user),
) -> PublishedQuizDiscoveryOut:
    """Find the published quiz for a node and check for in-progress attempts."""
    service = TraineeQuizService(db)
    return await service.get_published_quiz_state(
        node_id, current_user.sub, current_user.role
    )


@router.get(
    "/nodes/{node_id}/quizzes/{quiz_id}/attempts",
    response_model=TraineeQuizAttemptListOut,
)
async def list_quiz_attempts(
    node_id: UUID,
    quiz_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: TokenPayload = Depends(get_current_user),
) -> TraineeQuizAttemptListOut:
    """List all attempts for the trainee on this quiz, newest first."""
    service = TraineeQuizService(db)
    return await service.list_attempts(
        node_id, quiz_id, current_user.sub, current_user.role
    )


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
    """Trainee starts a new attempt on a published quiz."""
    service = TraineeQuizService(db)
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
    """Trainee submits or updates an answer for a question within an attempt."""
    service = TraineeQuizService(db)
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
    """Trainee submits the full attempt."""
    service = TraineeQuizService(db)
    return await service.submit_attempt(
        attempt_id, payload, current_user.sub, current_user.role
    )


@router.get(
    "/attempts/{attempt_id}",
    response_model=TraineeQuizOut,
)
async def get_quiz_attempt(
    attempt_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: TokenPayload = Depends(get_current_user),
) -> TraineeQuizOut:
    """Trainee resumes a mid-progress attempt or reviews details of a submitted one."""
    service = TraineeQuizService(db)
    return await service.get_attempt(attempt_id, current_user.sub, current_user.role)


@router.get(
    "/nodes/{node_id}/quizzes/archive",
    response_model=TraineeArchivedQuizListOut,
)
async def list_archived_quizzes(
    node_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: TokenPayload = Depends(get_current_user),
) -> TraineeArchivedQuizListOut:
    """List archived quizzes grouped by superseded study material version."""
    service = TraineeQuizService(db)
    return await service.list_archived_quizzes(
        node_id, current_user.sub, current_user.role
    )


@router.get(
    "/nodes/{node_id}/quizzes/{quiz_id}/review",
    response_model=ArchivedQuizReviewOut,
)
async def review_archived_quiz(
    node_id: UUID,
    quiz_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: TokenPayload = Depends(get_current_user),
) -> ArchivedQuizReviewOut:
    """Read-only review of an archived quiz with answers and explanations."""
    service = TraineeQuizService(db)
    return await service.review_archived_quiz(
        node_id, quiz_id, current_user.sub, current_user.role
    )
