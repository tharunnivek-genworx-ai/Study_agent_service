"""Persist hint generation outputs to topic-scoped artifact folders."""

from __future__ import annotations

from typing import Any

from src.api.utils.artifacts import log_agent_output
from src.api.utils.hint_utils.artifacts.hint_artifact_paths import (
    HINT_AGENT_ARTIFACT_SLUGS,
    PIPELINE_SUFFIX,
)


def log_hint_agent(
    *,
    topic_title: str,
    run_id: str,
    agent: str,
    payload: dict[str, Any],
    node_id: str | None = None,
) -> None:
    log_agent_output(
        topic_title=topic_title,
        run_id=run_id,
        agent=agent,
        payload=payload,
        pipeline_suffix=PIPELINE_SUFFIX,
        agent_slug_map=HINT_AGENT_ARTIFACT_SLUGS,
        flat_run_layout=True,
        node_id=node_id,
    )
