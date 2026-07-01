"""Shared dispatch for pipeline-specific generation resume executors."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any
from uuid import UUID

from src.api.schemas import GenerationRunResumeResult
from src.api.utils.space_node_utils.node_role_assert import _assert_mentor

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


async def execute_pipeline_resume(
    session: AsyncSession,
    resume_result: GenerationRunResumeResult,
    *,
    mentor_id: UUID,
    role: str,
    service_factory: Callable[[AsyncSession], Any],
    resume_fn: Callable[..., Awaitable[None]],
) -> None:
    """Assert mentor role, construct the service, and invoke its resume handler."""
    _assert_mentor(role)
    service = service_factory(session)
    await resume_fn(service, resume_result, user_id=mentor_id, role=role)
