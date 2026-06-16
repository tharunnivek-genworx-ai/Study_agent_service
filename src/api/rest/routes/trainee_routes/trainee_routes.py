# src/api/rest/routes/trainee_routes/trainee_routes.py
"""
Routes for trainee-side study material and quiz attempt operations.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, status
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.core.services.trainee_services.trainee_service import TraineeService
from src.api.data.clients.postgres.database import get_db
from src.api.rest.routes.dependencies import get_current_user
from src.api.schemas.identity_schemas.auth_schema import TokenPayload
from src.api.schemas.quiz_schemas.quiz_schema import (
    PublishedQuizDiscoveryOut,
    QuizAttemptOut,
    QuizAttemptStartRequest,
    QuizAttemptSubmitRequest,
    QuizQuestionResponseOut,
    QuizQuestionResponseRequest,
    TraineeQuizOut,
)
from src.api.schemas.study_material_schemas.study_material_schema import (
    TraineeStudyMaterialOut,
)

router = APIRouter(prefix="/trainee", tags=["Trainee"])


# ── Study Material ──────────────────────────────────────────────────────────


@router.get(
    "/nodes/{node_id}/study-material",
    response_model=TraineeStudyMaterialOut,
)
async def get_published_study_material(
    node_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: TokenPayload = Depends(get_current_user),
) -> TraineeStudyMaterialOut:
    """Trainee reads the published study material for a node."""
    service = TraineeService(db)
    return await service.get_published_study_material(
        node_id, current_user.sub, current_user.role
    )


@router.get(
    "/nodes/{node_id}/study-material/pdf",
)
async def download_published_study_material_pdf(
    node_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: TokenPayload = Depends(get_current_user),
) -> Response:
    """Trainee downloads the published study material as a PDF."""
    service = TraineeService(db)
    pdf_bytes, filename = await service.download_published_pdf(
        node_id, current_user.sub, current_user.role
    )
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ── Quizzes ─────────────────────────────────────────────────────────────────


@router.get(
    "/nodes/{node_id}/quizzes/published",
    response_model=PublishedQuizDiscoveryOut,
)
async def get_published_quiz_state(
    node_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: TokenPayload = Depends(get_current_user),
) -> PublishedQuizDiscoveryOut:
    """Finds the published quiz for a node and checks for in-progress attempts."""
    service = TraineeService(db)
    return await service.get_published_quiz_state(
        node_id, current_user.sub, current_user.role
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
    service = TraineeService(db)
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
    service = TraineeService(db)
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
    service = TraineeService(db)
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
    service = TraineeService(db)
    return await service.get_attempt(attempt_id, current_user.sub, current_user.role)
