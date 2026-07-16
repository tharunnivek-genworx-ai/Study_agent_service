"""Poll generation progress for study material and quiz pipelines."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.data.clients.postgres import get_db
from src.api.rest.routes.dependencies import get_current_user
from src.api.schemas import GenerationProgressOut
from src.api.schemas.identity_schemas import TokenPayload
from src.api.utils.generation_progress.db_store import DbGenerationProgressStore

router = APIRouter(tags=["Generation Progress"])


@router.get(
    "/generation-progress/{session_id}",
    response_model=GenerationProgressOut,
)
async def get_generation_progress(
    session_id: UUID,
    current_user: TokenPayload = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> GenerationProgressOut:
    """Return the current step for an in-flight or recently completed generation run.

    ``session_id`` is the durable ``run_id`` returned when generation starts.
    """
    db_store = DbGenerationProgressStore(session)
    progress_out = await db_store.to_progress_out_for_mentor(
        session_id,
        current_user.sub,
    )
    if progress_out is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Generation progress session not found.",
        )
    return progress_out
