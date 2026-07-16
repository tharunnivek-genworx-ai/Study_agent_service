# tests/test_quiz_overflow_prune.py
"""Tests for quiz count overflow → prune → present-without-QC path."""

from __future__ import annotations

import pytest

from src.api.control.quiz_agent.graph.quiz_graph.quiz_generation_graph import (
    _route_after_deterministic_validate,
    _route_after_quiz_generator,
)
from src.api.control.quiz_agent.nodes.quiz_graph.deterministic_validate_node import (
    deterministic_validate_node,
)
from src.api.utils.quiz_utils.graph.constants import QUESTION_PRUNE_MODE
from src.api.utils.quiz_utils.graph.node_helpers import _parse_remove_question_ids


def _question(question_id: str, text: str = "Q?", order_index: int = 0) -> dict:
    return {
        "question_id": question_id,
        "question_text": text,
        "option_a": "A",
        "option_b": "B",
        "option_c": "C",
        "option_d": "D",
        "correct_option": "A",
        "explanation": "Because A.",
        "difficulty": "easy",
        "domain": "Conceptual",
        "topic_tag": "Topic",
        "order_index": order_index,
    }


@pytest.mark.asyncio
async def test_overflow_routes_to_question_prune():
    questions = [_question(f"q{i}", f"Question {i}?", i) for i in range(9)]
    state = {
        "parsed_questions": questions,
        "question_count": 8,
        "gen_attempt": 0,
        "qc_retry_mode": "question_patch_then_insert",
        "node_title": "WW2",
    }
    result = await deterministic_validate_node(state)  # type: ignore[arg-type]
    assert result["struct_validation_passed"] is False
    assert result["qc_retry_mode"] == QUESTION_PRUNE_MODE
    assert "PRUNE REQUIRED" in result["gen_feedback"]
    assert _route_after_deterministic_validate({**state, **result}) == "quiz_generator"


@pytest.mark.asyncio
async def test_overflow_after_failed_prune_falls_back_and_skips_qc():
    questions = [_question(f"q{i}", f"Question {i}?", i) for i in range(10)]
    state = {
        "parsed_questions": questions,
        "question_count": 8,
        "gen_attempt": 1,
        "qc_retry_mode": QUESTION_PRUNE_MODE,
        "prune_attempt": 1,
        "qc_reverify_question_ids": ["q2"],
        "node_title": "WW2",
    }
    result = await deterministic_validate_node(state)  # type: ignore[arg-type]
    assert result["struct_validation_passed"] is True
    assert result["present_without_qc"] is True
    assert result["qc_passed"] is True
    assert len(result["validated_questions"]) == 8
    assert "q2" not in {q["question_id"] for q in result["validated_questions"]}
    assert (
        _route_after_deterministic_validate({**state, **result}) == "persist_quiz_draft"
    )


def test_prune_success_routes_to_persist_without_qc():
    state = {
        "present_without_qc": True,
        "struct_validation_passed": True,
        "parsed_questions": [_question("q1")],
        "qc_passed": True,
    }
    assert _route_after_quiz_generator(state) == "persist_quiz_draft"  # type: ignore[arg-type]
    assert _route_after_deterministic_validate(state) == "persist_quiz_draft"  # type: ignore[arg-type]


def test_parse_remove_question_ids():
    raw = '{"remove_question_ids": ["abc", "def"]}'
    assert _parse_remove_question_ids(raw) == ["abc", "def"]
