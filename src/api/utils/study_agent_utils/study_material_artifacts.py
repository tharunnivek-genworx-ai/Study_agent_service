"""Persist study-material generation outputs to topic-scoped artifact folders."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any

from src.api.utils.study_agent_utils.artifact_paths import (
    ensure_dir,
    study_material_log_path,
)

logger = logging.getLogger(__name__)


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
    """Write a JSON artifact under {topic}_SMG/."""
    try:
        out_path = study_material_log_path(topic_title, version_number, generation_type)
        ensure_dir(out_path.parent)
        payload = {
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
            "logged_at": datetime.now(UTC).isoformat(),
        }
        out_path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        logger.info("Study material artifact saved → %s", out_path)
    except OSError as exc:
        logger.warning("Could not save study material artifact: %s", exc)
