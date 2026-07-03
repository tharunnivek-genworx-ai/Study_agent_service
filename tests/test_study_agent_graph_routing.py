"""Tests for study_agent graph routing based on generation outcome."""

from __future__ import annotations

import pytest

from src.api.control.study_agent.graph.graph import _route_after_study_agent
from src.api.control.study_agent.graph.resume_router import route_after_study_agent
from src.api.utils.study_agent_utils.quality_check_utils.core.constants import (
    MAX_GENERATOR_FORMAT_ATTEMPTS,
)


@pytest.mark.parametrize(
    ("state", "expected"),
    [
        ({"terminal_llm_failure": True}, "__end__"),
        ({"error": "boom"}, "__end__"),
        ({"generation_outcome": "study_document"}, "quality_check"),
        ({"generation_outcome": "reference_required"}, "__end__"),
        ({"generation_outcome": "vague_feedback"}, "__end__"),
        ({"generation_outcome": "generator_error"}, "__end__"),
        (
            {
                "generation_outcome": "malformed_document",
                "generator_format_attempt": 0,
            },
            "study_agent",
        ),
        (
            {
                "generation_outcome": "malformed_document",
                "generator_format_attempt": MAX_GENERATOR_FORMAT_ATTEMPTS - 1,
            },
            "study_agent",
        ),
        (
            {
                "generation_outcome": "malformed_document",
                "generator_format_attempt": MAX_GENERATOR_FORMAT_ATTEMPTS,
            },
            "__end__",
        ),
    ],
)
def test_route_after_study_agent_matrix(state: dict, expected: str) -> None:
    assert route_after_study_agent(state) == expected
    assert _route_after_study_agent(state) == expected


def test_route_after_study_agent_legacy_checkpoint_falls_back_to_qc() -> None:
    state = {"generated_content": '{"sections": []}'}
    assert route_after_study_agent(state) == "quality_check"
