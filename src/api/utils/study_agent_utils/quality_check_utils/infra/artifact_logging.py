"""QC artifact logging helpers."""

from __future__ import annotations

from typing import Any

from src.api.control.study_agent.states.state import StudyMaterialGraphState
from src.api.utils.study_agent_utils.artifacts.study_material_artifacts import (
    log_agent_output,
)


def pipeline_attempt(state: StudyMaterialGraphState) -> int:
    return (state.get("qc_attempt") or 0) + 1


def log_qc_agent(
    state: StudyMaterialGraphState,
    *,
    agent: str,
    pipeline_attempt: int,
    payload: dict[str, Any],
) -> None:
    run_id = state.get("artifact_run_id")
    if not run_id:
        return
    log_agent_output(
        topic_title=state.get("node_title") or str(state.get("node_id")),
        run_id=run_id,
        agent=agent,
        pipeline_attempt=pipeline_attempt,
        node_id=str(state.get("node_id") or ""),
        generation_type=state.get("generation_mode") or "generate",
        payload=payload,
    )
