"""Unit tests for study material resume routing."""

from __future__ import annotations

from uuid import uuid4

from src.api.control.study_agent.graph.resume_router import (
    hydrate_checkpoint_state,
    resolve_resume_next_node,
)


def test_resolve_resume_after_concept_checklist_skips_to_study_agent() -> None:
    state = {
        "generation_mode": "generate",
        "must_cover_checklist": [{"id": "c1", "concept": "loops"}],
        "domain": "Programming",
    }
    assert (
        resolve_resume_next_node(state, last_completed_node="concept_checklist")
        == "study_agent"
    )


def test_resolve_resume_after_concept_checklist_without_plan_retries_checklist() -> (
    None
):
    state = {"generation_mode": "generate"}
    assert (
        resolve_resume_next_node(state, last_completed_node="concept_checklist")
        == "concept_checklist"
    )


def test_resolve_resume_after_study_agent_enters_quality_check() -> None:
    state = {
        "generated_content": '{"sections": [{"id": "s1", "heading": "Intro"}]}',
    }
    assert (
        resolve_resume_next_node(state, last_completed_node="study_agent")
        == "quality_check"
    )


def test_resolve_resume_after_quality_check_infra_error_retries_qc() -> None:
    state = {
        "generated_content": '{"sections": []}',
        "qc_result": {"qcInfraError": True},
    }
    assert (
        resolve_resume_next_node(state, last_completed_node="quality_check")
        == "quality_check"
    )


def test_resolve_resume_after_quality_check_section_patch_enters_study_agent() -> None:
    state = {
        "generated_content": '{"sections": []}',
        "qc_retry_mode": "section_patch",
        "qc_section_failures": [{"section_id": "s1", "failures": []}],
        "qc_frozen_check_ids": ["c1"],
        "qc_frozen_section_keys": ["s2"],
    }
    assert (
        resolve_resume_next_node(state, last_completed_node="quality_check")
        == "study_agent"
    )


def test_resolve_resume_after_resolver_with_reference_goes_to_llamaparse() -> None:
    state = {
        "has_reference_material": True,
        "reference_file_path": "/tmp/ref.pdf",
        "skip_llamaparse": False,
    }
    assert (
        resolve_resume_next_node(state, last_completed_node="resolver") == "llamaparse"
    )


def test_hydrate_checkpoint_state_sets_resume_flags() -> None:
    node_id = uuid4()
    state = hydrate_checkpoint_state(
        {
            "node_id": str(node_id),
            "must_cover_checklist": [{"id": "c1"}],
            "generation_mode": "generate",
        },
        last_completed_node="concept_checklist",
        request_params={"reference_material_id": None},
    )
    assert state["node_id"] == node_id
    assert state["_is_resume"] is True
    assert state["_last_completed_node"] == "concept_checklist"
    assert state["must_cover_checklist"] == [{"id": "c1"}]
