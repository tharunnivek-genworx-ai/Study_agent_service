"""Entry point for running the hint generation LangGraph.

The service layer calls ``run_hint_generation`` for fresh runs or
``run_hint_from_checkpoint`` after ``hydrate_checkpoint_state``. Both delegate
to ``_run_graph``, which:

1. Obtains the cached compiled graph from ``get_hint_generation_graph``.
2. Invokes it via ``invoke_graph_with_progress`` (checkpointing + progress
   hooks for the HINT pipeline).
3. Interprets the final state:
   - ``terminal_llm_failure`` → return state (diagnostics already persisted
     by the graph's failure node); no exception.
   - ``error`` → raise ``HintGenerationFailedException``.
   - otherwise → return successful final state.

The AsyncSession and optional ``run_id`` are passed through LangGraph
``config["configurable"]`` so nodes can access DB and artifact logging.
"""

from __future__ import annotations

import logging
from typing import Any, cast
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.api.control.hint_agent.graph.hint_generation_graph import (
    get_hint_generation_graph,
)
from src.api.control.hint_agent.states.hint_state import HintGraphState
from src.api.core.exceptions import (
    HintGenerationFailedException,
)
from src.api.utils.generation_progress import (
    GenerationPipeline,
    invoke_graph_with_progress,
)

logger = logging.getLogger(__name__)


async def _run_graph(
    session: AsyncSession,
    initial_state: HintGraphState,
    *,
    run_id: UUID | None = None,
) -> HintGraphState:
    """Execute the hint graph and map terminal state to return or raise.

    Shared implementation for fresh and checkpoint-resume entry points.
    Progress/checkpointing is handled by ``invoke_graph_with_progress``; this
    function only configures the graph and interprets the outcome.
    """
    graph = get_hint_generation_graph()
    config = {
        "configurable": {
            "session": session,
            "run_id": str(run_id) if run_id is not None else None,
            "pipeline": GenerationPipeline.HINT.value,
        }
    }
    result = cast(
        HintGraphState,
        await invoke_graph_with_progress(
            graph,
            cast(dict[str, Any], initial_state),
            config,
            pipeline=GenerationPipeline.HINT,
            run_id=run_id,
        ),
    )

    if result.get("terminal_llm_failure"):
        # Graph persisted diagnostics; return state for caller to inspect.
        logger.warning(
            "Hint LLM generation failed (%s) for quiz '%s' — persisting diagnostics.",
            result.get("llm_error_type"),
            result.get("quiz_id"),
        )
        return result

    if result.get("error"):
        # Non-terminal pipeline error — surface to API layer.
        detail = str(result["error"])
        logger.error("Hint generation failed: %s", detail)
        raise HintGenerationFailedException(detail)

    return result


async def run_hint_generation(
    session: AsyncSession,
    initial_state: HintGraphState,
    *,
    run_id: UUID | None = None,
) -> HintGraphState:
    """Fresh hint generation from service-shaped initial state.

    Expects ``initial_state`` without resume flags (``node_id``, ``quiz_id``,
    ``mentor_id``, optional ``questions_filter_ids`` / ``mentor_feedback``).
    The graph entry router will start at ``load_hint_context``.
    """
    return await _run_graph(
        session,
        initial_state,
        run_id=run_id,
    )


async def run_hint_from_checkpoint(
    session: AsyncSession,
    initial_state: HintGraphState,
    *,
    run_id: UUID | None = None,
) -> HintGraphState:
    """Resume a failed hint run from a hydrated checkpoint state.

    ``initial_state`` should come from ``hydrate_checkpoint_state`` with
    ``RESUME_FLAG`` and ``LAST_COMPLETED_NODE_KEY`` set so the entry router
    jumps to the appropriate node.
    """
    return await _run_graph(
        session,
        initial_state,
        run_id=run_id,
    )
