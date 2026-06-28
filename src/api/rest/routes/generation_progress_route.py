"""Poll generation progress for study material and quiz pipelines."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.data.clients.postgres.database import get_db
from src.api.rest.routes.dependencies import get_current_user
from src.api.schemas.generation_progress_schema import GenerationProgressOut
from src.api.schemas.identity_schemas.auth_schema import TokenPayload
from src.api.utils.generation_progress import get_generation_progress_store
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
    """Return the current step for an in-flight or recently completed generation job."""
    del current_user  # auth gate only

    db_store = DbGenerationProgressStore(session)
    progress_out = await db_store.to_progress_out(session_id)
    if progress_out is not None:
        return progress_out

    # Backward compat: legacy in-memory sessions keyed by client progress_session_id.
    store = get_generation_progress_store()
    legacy_out = store.to_progress_out(str(session_id))
    if legacy_out is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Generation progress session not found.",
        )
    return legacy_out
