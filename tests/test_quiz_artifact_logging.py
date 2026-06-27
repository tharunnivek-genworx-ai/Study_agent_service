# tests/test_quiz_artifact_logging.py
"""Unit tests for quiz artifact path resolution."""

from __future__ import annotations

from src.api.utils.quiz_utils.artifacts.quiz_artifact_paths import (
    quiz_agent_artifact_path,
)


class TestQuizArtifactPaths:
    def test_generator_path_uses_qg_suffix_and_attempt_folder(self):
        path = quiz_agent_artifact_path(
            "useState",
            "20260627_124847",
            "quiz_generator",
            pipeline_attempt=1,
        )
        path_str = str(path).replace("\\", "/")
        assert (
            "useState_QG/run_20260627_124847/attempt01/02_quiz_generator.json"
            in path_str
        )
