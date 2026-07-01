"""Persist quiz generation outputs to topic-scoped artifact folders."""

from __future__ import annotations

from typing import Any

from src.api.utils.artifacts import ist_timestamp, log_agent_output, write_json
from src.api.utils.quiz_utils.artifacts.quiz_artifact_paths import (
    PIPELINE_SUFFIX,
    QUIZ_AGENT_ARTIFACT_SLUGS,
    quiz_topic_dir,
)


def log_quiz_agent(
    *,
    topic_title: str,
    run_id: str,
    agent: str,
    payload: dict[str, Any],
    pipeline_attempt: int | None = None,
    node_id: str | None = None,
    mode: str | None = None,
) -> None:
    log_agent_output(
        topic_title=topic_title,
        run_id=run_id,
        agent=agent,
        payload=payload,
        pipeline_suffix=PIPELINE_SUFFIX,
        agent_slug_map=QUIZ_AGENT_ARTIFACT_SLUGS,
        pipeline_attempt=pipeline_attempt,
        node_id=node_id,
        generation_type=mode,
    )


def log_quiz_draft_snapshot(
    *,
    topic_title: str,
    quiz_id: str,
    payload: dict[str, Any],
) -> None:
    """Write post-persist quiz draft snapshot at topic root."""
    try:
        filename = f"quiz_draft_{quiz_id}_{ist_timestamp()}.json"
        out_path = quiz_topic_dir(topic_title) / filename
        write_json(out_path, payload)
    except OSError:
        pass
