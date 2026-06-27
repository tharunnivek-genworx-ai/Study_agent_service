"""Topic-scoped artifact paths for hint generation (HG pipeline)."""

from __future__ import annotations

from pathlib import Path

from src.api.utils.artifacts.common import agent_artifact_path, topic_dir

PIPELINE_SUFFIX = "HG"

HINT_AGENT_ARTIFACT_SLUGS: dict[str, str] = {
    "hint_generator": "02_hint_generator",
    "hint_validation": "03_hint_validation",
    "hint_result": "04_hint_result",
}


def hint_topic_dir(topic_title: str) -> Path:
    return topic_dir(topic_title, PIPELINE_SUFFIX)


def hint_agent_artifact_path(topic_title: str, run_id: str, agent: str) -> Path:
    return agent_artifact_path(
        topic_title,
        run_id,
        agent,
        pipeline_suffix=PIPELINE_SUFFIX,
        agent_slug_map=HINT_AGENT_ARTIFACT_SLUGS,
        flat_run_layout=True,
    )
