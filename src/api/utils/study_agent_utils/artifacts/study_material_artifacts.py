"""Persist study-material generation outputs to topic-scoped artifact folders."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from src.api.utils.study_agent_utils.artifacts.artifact_paths import (
    agent_artifact_path,
    ensure_dir,
    ist_timestamp,
    study_material_log_path,
)

logger = logging.getLogger(__name__)


def _json_default(obj: Any) -> Any:
    """Serialize non-JSON-native values for artifact files."""
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    ensure_dir(path.parent)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, default=_json_default),
        encoding="utf-8",
    )


def log_agent_output(
    *,
    topic_title: str,
    run_id: str,
    agent: str,
    payload: dict[str, Any],
    pipeline_attempt: int | None = None,
    node_id: str | None = None,
    generation_type: str | None = None,
) -> None:
    """Write one agent's output under {topic}_SMG/run_{run_id}/."""
    try:
        out_path = agent_artifact_path(
            topic_title,
            run_id,
            agent,
            pipeline_attempt=pipeline_attempt,
        )
        envelope: dict[str, Any] = {
            "agent": agent,
            "run_id": run_id,
            "logged_at": datetime.now(UTC).isoformat(),
        }
        if pipeline_attempt is not None:
            envelope["pipeline_attempt"] = pipeline_attempt
        if node_id is not None:
            envelope["node_id"] = node_id
        if generation_type is not None:
            envelope["generation_type"] = generation_type
        envelope.update(payload)
        _write_json(out_path, envelope)
        logger.info("Agent artifact saved → %s", out_path)
    except OSError as exc:
        logger.warning("Could not save %s artifact: %s", agent, exc)


def log_study_material_version(
    *,
    topic_title: str,
    version_number: int,
    generation_type: str,
    version_id: str,
    node_id: str,
    content: str,
    graph_result: dict[str, Any],
    mentor_feedback_used: str | None = None,
) -> None:
    """Write final persisted version snapshot under {topic}_SMG/."""
    try:
        out_path = study_material_log_path(topic_title, version_number, generation_type)
        payload = {
            "artifact_kind": "persisted_version",
            "version_id": version_id,
            "node_id": node_id,
            "version_number": version_number,
            "generation_type": generation_type,
            "mentor_feedback_used": mentor_feedback_used,
            "content": content,
            "llm_model_used": graph_result.get("llm_model_used"),
            "token_usage": graph_result.get("token_usage"),
            "prompt_snapshot": graph_result.get("prompt_snapshot"),
            "qc_failed_permanently": graph_result.get("qc_failed_permanently", False),
            "qc_result": graph_result.get("qc_result"),
            "must_cover_checklist": graph_result.get("must_cover_checklist"),
            "qc_llm_model_used": graph_result.get("qc_llm_model_used"),
            "qc_llm_models_used": graph_result.get("qc_llm_models_used"),
            "checklist_llm_model_used": graph_result.get("checklist_llm_model_used"),
            "artifact_run_id": graph_result.get("artifact_run_id"),
            "logged_at": datetime.now(UTC).isoformat(),
        }
        _write_json(out_path, payload)
        logger.info("Study material version artifact saved → %s", out_path)
    except OSError as exc:
        logger.warning("Could not save study material version artifact: %s", exc)


def new_artifact_run_id() -> str:
    """IST timestamp identifying one end-to-end graph execution."""
    return ist_timestamp()
