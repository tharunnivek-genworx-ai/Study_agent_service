"""Cooperative abort helpers for external research (LlamaParse-style)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any
from uuid import UUID

from langchain_core.runnables import RunnableConfig

from src.api.core.exceptions import GenerationRunAborted

ShouldContinueAsync = Callable[[], Awaitable[bool]]


async def abort_if_should_stop(should_continue: ShouldContinueAsync | None) -> None:
    """Raise GenerationRunAborted when the run token says stop."""
    if should_continue is not None and not await should_continue():
        raise GenerationRunAborted()


def build_should_continue_from_config(
    config: RunnableConfig | dict[str, Any] | None,
) -> ShouldContinueAsync | None:
    """Build an async should-continue check from graph configurable run ids."""
    if not config:
        return None
    configurable = config.get("configurable") or {}
    session = configurable.get("session")
    run_id_raw = configurable.get("run_id")
    execution_token_raw = configurable.get("execution_token")
    if session is None or run_id_raw is None or execution_token_raw is None:
        return None

    run_id = UUID(str(run_id_raw))
    execution_token = UUID(str(execution_token_raw))

    async def _token_check() -> bool:
        from src.api.core.services.generation_run_service import GenerationRunService

        run_service = GenerationRunService(session)
        return await run_service.should_continue_execution(run_id, execution_token)

    return _token_check
