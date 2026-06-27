"""Topic-scoped artifact paths for quiz generation (QG pipeline)."""

from __future__ import annotations

from pathlib import Path

from src.api.utils.artifacts.common import (
    agent_artifact_path,
    pipeline_attempt_dir,
    run_artifact_dir,
    topic_dir,
)

PIPELINE_SUFFIX = "QG"

QUIZ_AGENT_ARTIFACT_SLUGS: dict[str, str] = {
    "quiz_generator": "02_quiz_generator",
    "quiz_deterministic": "03_quiz_deterministic",
    "quiz_qc_verification": "04_quiz_qc_verification",
    "quiz_qc_result": "05_quiz_qc_result",
}


def quiz_topic_dir(topic_title: str) -> Path:
    return topic_dir(topic_title, PIPELINE_SUFFIX)


def quiz_run_dir(topic_title: str, run_id: str) -> Path:
    return run_artifact_dir(topic_title, PIPELINE_SUFFIX, run_id)


def quiz_attempt_dir(topic_title: str, run_id: str, pipeline_attempt: int) -> Path:
    return pipeline_attempt_dir(topic_title, PIPELINE_SUFFIX, run_id, pipeline_attempt)


def quiz_agent_artifact_path(
    topic_title: str,
    run_id: str,
    agent: str,
    *,
    pipeline_attempt: int | None = None,
) -> Path:
    return agent_artifact_path(
        topic_title,
        run_id,
        agent,
        pipeline_suffix=PIPELINE_SUFFIX,
        agent_slug_map=QUIZ_AGENT_ARTIFACT_SLUGS,
        pipeline_attempt=pipeline_attempt,
    )
