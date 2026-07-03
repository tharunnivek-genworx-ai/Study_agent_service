"""Tests that quality_check_node only processes study_document outcomes."""

from __future__ import annotations

import asyncio
from unittest.mock import patch
from uuid import uuid4

import pytest

from src.api.control.study_agent.nodes.quality_check_node import quality_check_node


@pytest.mark.parametrize(
    "outcome",
    ["reference_required", "vague_feedback", "malformed_document", "generator_error"],
)
def test_qc_guard_returns_for_non_study_outcome(outcome: str) -> None:
    state = {
        "generation_outcome": outcome,
        "generated_content": '{"generation_status":"reference_required"}',
        "generation_parsed_document": {"generation_status": "reference_required"},
        "qc_attempt": 0,
    }

    result = asyncio.run(quality_check_node(state, config={}))

    assert result["qc_evaluated"] is False
    assert result["qc_passed"] is False
    assert result["qc_attempt"] == 0


def test_qc_guard_missing_parsed_document() -> None:
    state = {
        "generation_outcome": "study_document",
        "generated_content": '{"sections": []}',
        "generation_parsed_document": None,
        "qc_attempt": 1,
    }

    result = asyncio.run(quality_check_node(state, config={}))

    assert result["qc_evaluated"] is False
    assert result["qc_passed"] is False


def test_qc_proceeds_past_guard_for_study_document() -> None:
    state = {
        "generation_outcome": "study_document",
        "generated_content": '{"sections": [{"id": "s1", "heading": "Intro", "content": "x"}]}',
        "generation_parsed_document": {
            "sections": [{"id": "s1", "heading": "Intro", "content": "x"}]
        },
        "node_id": uuid4(),
        "node_title": "Test Topic",
        "effective_instruction": "Teach basics.",
        "qc_attempt": 0,
    }

    with patch(
        "src.api.control.study_agent.nodes.quality_check_node.helpers.groq_api_keys_configured",
        return_value=False,
    ):
        result = asyncio.run(quality_check_node(state, config={}))

    assert result["qc_attempt"] == 1
    assert result["qc_passed"] is False
    qc_result = result.get("qc_result") or {}
    assert qc_result.get("qcInfraError") is True
