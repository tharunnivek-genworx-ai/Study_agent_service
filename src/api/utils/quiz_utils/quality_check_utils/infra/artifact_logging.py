"""QC artifact logging helpers for quiz generation."""

from __future__ import annotations

from typing import Any

from src.api.control.quiz_agent.states.quiz_state import QuizGraphState
from src.api.utils.quiz_utils.artifacts.quiz_artifacts import log_quiz_agent


def pipeline_attempt(state: QuizGraphState) -> int:
    return max(state.get("qc_attempt") or 0, state.get("gen_attempt") or 0) + 1


def log_qc_agent(
    state: QuizGraphState,
    *,
    agent: str,
    pipeline_attempt: int,
    payload: dict[str, Any],
) -> None:
    run_id = state.get("artifact_run_id")
    if not run_id:
        return
    log_quiz_agent(
        topic_title=state.get("node_title") or str(state.get("node_id")),
        run_id=run_id,
        agent=agent,
        pipeline_attempt=pipeline_attempt,
        node_id=str(state.get("node_id") or ""),
        mode=state.get("mode") or "generate",
        payload=payload,
    )
