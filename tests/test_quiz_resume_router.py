"""Unit tests for quiz generation resume routing."""

from __future__ import annotations

from uuid import uuid4

from src.api.control.quiz_agent.graph.quiz_graph.resume_router import (
    hydrate_checkpoint_state,
    resolve_resume_next_node,
)


def test_resolve_resume_after_load_context_skips_to_quiz_generator() -> None:
    state = {
        "mode": "generate",
        "study_material_content": "Variables and loops.",
        "study_material_version_id": str(uuid4()),
    }
    assert (
        resolve_resume_next_node(state, last_completed_node="load_generation_context")
        == "quiz_generator"
    )


def test_resolve_resume_after_load_context_regenerate_loads_existing() -> None:
    state = {
        "mode": "regenerate",
        "study_material_content": "Content.",
        "quiz_id": str(uuid4()),
    }
    assert (
        resolve_resume_next_node(state, last_completed_node="load_generation_context")
        == "load_existing_quiz_if_regenerate"
    )


def test_resolve_resume_after_quiz_generator_skips_parse_when_parsed() -> None:
    state = {
        "parsed_questions": [{"question_id": "q1", "question_text": "What is x?"}],
    }
    assert (
        resolve_resume_next_node(state, last_completed_node="quiz_generator")
        == "deterministic_validate"
    )


def test_resolve_resume_after_quiz_generator_enters_parse_with_raw_output() -> None:
    state = {
        "raw_llm_output": '[{"question_text": "Q?"}]',
    }
    assert (
        resolve_resume_next_node(state, last_completed_node="quiz_generator")
        == "parse_quiz_output"
    )


def test_resolve_resume_after_quality_check_infra_error_retries_qc() -> None:
    state = {
        "validated_questions": [{"question_id": "q1"}],
        "qc_result": {"qcInfraError": True},
    }
    assert (
        resolve_resume_next_node(state, last_completed_node="quality_check")
        == "quality_check"
    )


def test_resolve_resume_after_quality_check_question_patch_enters_generator() -> None:
    state = {
        "validated_questions": [{"question_id": "q1"}, {"question_id": "q2"}],
        "qc_retry_mode": "question_patch",
        "qc_question_failures": [{"question_id": "q2", "failures": []}],
        "qc_frozen_question_ids": ["q1"],
    }
    assert (
        resolve_resume_next_node(state, last_completed_node="quality_check")
        == "quiz_generator"
    )


def test_resolve_resume_after_deterministic_fail_retries_generator() -> None:
    state = {
        "struct_validation_passed": False,
        "gen_feedback": "Missing option D on Q3.",
    }
    assert (
        resolve_resume_next_node(state, last_completed_node="deterministic_validate")
        == "quiz_generator"
    )


def test_hydrate_checkpoint_state_sets_resume_flags() -> None:
    node_id = uuid4()
    quiz_id = uuid4()
    state = hydrate_checkpoint_state(
        {
            "node_id": str(node_id),
            "quiz_id": str(quiz_id),
            "validated_questions": [{"question_id": "q1"}],
            "mode": "regenerate",
        },
        last_completed_node="quality_check",
        request_params={"question_count": 10, "difficulty": "mixed"},
    )
    assert state["node_id"] == node_id
    assert state["quiz_id"] == quiz_id
    assert state["_is_resume"] is True
    assert state["_last_completed_node"] == "quality_check"
    assert state["question_count"] == 10
