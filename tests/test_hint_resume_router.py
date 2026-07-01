"""Unit tests for hint generation resume routing."""

from __future__ import annotations

from uuid import uuid4

from src.api.control.hint_agent.graph.resume_router import (
    hydrate_checkpoint_state,
    resolve_resume_next_node,
)


def test_resolve_resume_after_load_context_skips_to_build_prompt() -> None:
    state = {
        "questions_for_hinting": [{"question_id": "q1"}],
        "node_title": "Variables",
    }
    assert (
        resolve_resume_next_node(state, last_completed_node="load_hint_context")
        == "build_hint_prompt_payload"
    )


def test_resolve_resume_after_invoke_skips_to_parse_with_raw_output() -> None:
    state = {
        "raw_llm_output": '[{"question_id": "q1", "hint_1": "a", "hint_2": "b", "hint_3": "c"}]'
    }
    assert (
        resolve_resume_next_node(state, last_completed_node="invoke_hint_llm")
        == "parse_hint_output"
    )


def test_resolve_resume_after_invoke_llm_failure_persists_diagnostics() -> None:
    state = {"terminal_llm_failure": True}
    assert (
        resolve_resume_next_node(state, last_completed_node="invoke_hint_llm")
        == "persist_hint_failure_diagnostics"
    )


def test_resolve_resume_after_parse_error_retries_invoke_without_raw_output() -> None:
    state = {"error": "Malformed hint output"}
    assert (
        resolve_resume_next_node(state, last_completed_node="parse_hint_output")
        == "invoke_hint_llm"
    )


def test_resolve_resume_after_validate_with_failures_retries_validation() -> None:
    state = {
        "questions_for_hinting": [
            {"question_id": "q1"},
            {"question_id": "q2"},
        ],
        "hints_written": {
            "q1": {
                "question_id": "q1",
                "hint_1": "a",
                "hint_2": "b",
                "hint_3": "c",
            }
        },
        "failed_question_ids": ["q2"],
    }
    assert (
        resolve_resume_next_node(state, last_completed_node="validate_hint_quality")
        == "validate_hint_quality"
    )


def test_resolve_resume_after_validate_without_failures_persists() -> None:
    state = {
        "questions_for_hinting": [{"question_id": "q1"}],
        "hints_written": {
            "q1": {
                "question_id": "q1",
                "hint_1": "a",
                "hint_2": "b",
                "hint_3": "c",
            }
        },
        "failed_question_ids": [],
    }
    assert (
        resolve_resume_next_node(state, last_completed_node="validate_hint_quality")
        == "persist_hints_to_questions"
    )


def test_hydrate_checkpoint_state_sets_resume_flags() -> None:
    node_id = uuid4()
    quiz_id = uuid4()
    state = hydrate_checkpoint_state(
        {
            "node_id": str(node_id),
            "quiz_id": str(quiz_id),
            "hints_written": {"q1": {"hint_1": "a", "hint_2": "b", "hint_3": "c"}},
        },
        last_completed_node="validate_hint_quality",
        request_params={"mentor_feedback": "Be more Socratic"},
    )
    assert state["node_id"] == node_id
    assert state["quiz_id"] == quiz_id
    assert state["_is_resume"] is True
    assert state["_last_completed_node"] == "validate_hint_quality"
    assert state["mentor_feedback"] == "Be more Socratic"
