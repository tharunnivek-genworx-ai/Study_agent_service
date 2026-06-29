# src/api/rest/routes/quiz_routes/hint_route.py
"""
Routes for hint generation on existing quiz questions.

Hint lifecycle (separate LangGraph flow from quiz question generation):
  MENTOR:
    Generate hints    → POST /nodes/{node_id}/quizzes/{quiz_id}/hints/generate
    Regenerate hints  → POST /nodes/{node_id}/quizzes/{quiz_id}/hints/regenerate

The quiz and its questions must already exist in the database before
hint generation can run.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.core.services import HintService
from src.api.data.clients.postgres import get_db
from src.api.rest.routes.dependencies import get_current_user
from src.api.schemas.identity_schemas import TokenPayload
from src.api.schemas.quiz_schemas import (
    HintGenerateRequest,
    HintRegenerateRequest,
    QuizOut,
)

router = APIRouter(tags=["Quiz Hints"])


@router.post(
    "/nodes/{node_id}/quizzes/{quiz_id}/hints/generate",
    status_code=status.HTTP_200_OK,
    response_model=QuizOut,
)
async def generate_hints(
    node_id: UUID,
    quiz_id: UUID,
    payload: HintGenerateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: TokenPayload = Depends(get_current_user),
) -> QuizOut:
    """Mentor generates hints for all active questions missing hints.

    Requires a persisted, unpublished quiz with finalized question rows.
    Returns the updated QuizOut with hints populated on all questions.
    """
    service = HintService(db)
    return await service.generate_hints(
        node_id, quiz_id, payload, current_user.sub, current_user.role
    )


@router.post(
    "/nodes/{node_id}/quizzes/{quiz_id}/hints/regenerate",
    status_code=status.HTTP_200_OK,
    response_model=QuizOut,
)
async def regenerate_hints(
    node_id: UUID,
    quiz_id: UUID,
    payload: HintRegenerateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: TokenPayload = Depends(get_current_user),
) -> QuizOut:
    """Mentor regenerates hints for specific questions after draft edits.

    question_ids must be the complete set of questions to overwrite —
    typically those edited since the last hint generation pass.
    Returns the updated QuizOut with refreshed hints for the specified questions.
    """
    service = HintService(db)
    return await service.regenerate_hints(
        node_id, quiz_id, payload, current_user.sub, current_user.role
    )


@router.delete(
    "/nodes/{node_id}/quizzes/{quiz_id}/hints",
    status_code=status.HTTP_200_OK,
    response_model=QuizOut,
)
async def delete_hints_draft(
    node_id: UUID,
    quiz_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: TokenPayload = Depends(get_current_user),
) -> QuizOut:
    """Mentor clears all generated hints on an unpublished quiz draft."""
    service = HintService(db)
    return await service.delete_hints_draft(
        node_id, quiz_id, current_user.sub, current_user.role
    )
