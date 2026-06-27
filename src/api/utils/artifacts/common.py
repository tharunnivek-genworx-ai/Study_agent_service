"""Shared artifact utilities for all agent pipelines."""

from __future__ import annotations

import json
import logging
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

ARTIFACTS_ROOT = Path("/app/uploads/artifacts")
IST = ZoneInfo("Asia/Kolkata")


def slugify_topic(title: str, *, max_length: int = 60) -> str:
    """Filesystem-safe slug from a topic title."""
    slug = re.sub(r"[^\w\s-]", "", title.strip(), flags=re.UNICODE)
    slug = re.sub(r"[\s_-]+", "_", slug).strip("_")
    if not slug:
        slug = "topic"
    return slug[:max_length]


def ist_timestamp() -> str:
    """Compact IST timestamp for folder and file names."""
    return datetime.now(IST).strftime("%Y%m%d_%H%M%S")


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def new_artifact_run_id() -> str:
    """IST timestamp identifying one end-to-end graph execution."""
    return ist_timestamp()


def _json_default(obj: Any) -> Any:
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


def write_json(path: Path, payload: dict[str, Any]) -> None:
    ensure_dir(path.parent)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, default=_json_default),
        encoding="utf-8",
    )


def topic_dir(topic_title: str, pipeline_suffix: str) -> Path:
    """e.g. uploads/artifacts/useState_QG/"""
    return ARTIFACTS_ROOT / f"{slugify_topic(topic_title)}_{pipeline_suffix}"


def run_artifact_dir(
    topic_title: str,
    pipeline_suffix: str,
    run_id: str,
) -> Path:
    """e.g. uploads/artifacts/useState_QG/run_20260627_124847/"""
    return topic_dir(topic_title, pipeline_suffix) / f"run_{run_id}"


def pipeline_attempt_dir(
    topic_title: str,
    pipeline_suffix: str,
    run_id: str,
    pipeline_attempt: int,
) -> Path:
    """e.g. .../useState_QG/run_20260627_124847/attempt01/"""
    return (
        run_artifact_dir(topic_title, pipeline_suffix, run_id)
        / f"attempt{pipeline_attempt:02d}"
    )


def agent_artifact_path(
    topic_title: str,
    run_id: str,
    agent: str,
    *,
    pipeline_suffix: str,
    agent_slug_map: dict[str, str],
    pipeline_attempt: int | None = None,
    flat_run_layout: bool = False,
) -> Path:
    """Resolve per-agent JSON path under a run folder."""
    slug = agent_slug_map.get(agent, agent)
    filename = f"{slug}.json"
    base = run_artifact_dir(topic_title, pipeline_suffix, run_id)
    if flat_run_layout:
        return base / filename
    attempt = pipeline_attempt or 1
    return (
        pipeline_attempt_dir(topic_title, pipeline_suffix, run_id, attempt) / filename
    )


def log_agent_output(
    *,
    topic_title: str,
    run_id: str,
    agent: str,
    payload: dict[str, Any],
    pipeline_suffix: str,
    agent_slug_map: dict[str, str],
    pipeline_attempt: int | None = None,
    flat_run_layout: bool = False,
    node_id: str | None = None,
    generation_type: str | None = None,
) -> None:
    """Write one agent's output under {topic}_{suffix}/run_{run_id}/."""
    try:
        out_path = agent_artifact_path(
            topic_title,
            run_id,
            agent,
            pipeline_suffix=pipeline_suffix,
            agent_slug_map=agent_slug_map,
            pipeline_attempt=pipeline_attempt,
            flat_run_layout=flat_run_layout,
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
        write_json(out_path, envelope)
        logger.info("Agent artifact saved → %s", out_path)
    except OSError as exc:
        logger.warning("Could not save %s artifact: %s", agent, exc)
