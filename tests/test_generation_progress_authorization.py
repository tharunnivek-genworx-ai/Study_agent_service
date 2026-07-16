"""Authorization checks for durable generation progress polling."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

from src.api.rest.routes import generation_progress_route
from src.api.utils.generation_progress.db_store import DbGenerationProgressStore


@pytest.mark.asyncio
async def test_progress_lookup_is_scoped_to_authenticated_mentor() -> None:
    run_id = uuid4()
    mentor_id = uuid4()
    expected = MagicMock()
    current_user = MagicMock(sub=mentor_id)

    with patch.object(
        generation_progress_route,
        "DbGenerationProgressStore",
    ) as store_class:
        store_class.return_value.to_progress_out_for_mentor = AsyncMock(
            return_value=expected,
        )
        result = await generation_progress_route.get_generation_progress(
            session_id=run_id,
            current_user=current_user,
            session=MagicMock(),
        )

    assert result is expected
    store_class.return_value.to_progress_out_for_mentor.assert_awaited_once_with(
        run_id,
        mentor_id,
    )


@pytest.mark.asyncio
async def test_foreign_or_missing_progress_run_returns_not_found() -> None:
    with patch.object(
        generation_progress_route,
        "DbGenerationProgressStore",
    ) as store_class:
        store_class.return_value.to_progress_out_for_mentor = AsyncMock(
            return_value=None,
        )
        with pytest.raises(HTTPException) as exc_info:
            await generation_progress_route.get_generation_progress(
                session_id=uuid4(),
                current_user=MagicMock(sub=uuid4()),
                session=MagicMock(),
            )

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_progress_store_rejects_foreign_run_before_serializing() -> None:
    store = DbGenerationProgressStore(MagicMock())
    store._repo = MagicMock()
    store._repo.get_by_id = AsyncMock(
        return_value=MagicMock(mentor_id=uuid4()),
    )
    store.get_record = AsyncMock()

    result = await store.to_progress_out_for_mentor(uuid4(), uuid4())

    assert result is None
    store.get_record.assert_not_awaited()
