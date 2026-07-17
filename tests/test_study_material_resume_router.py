"""Unit tests for study material resume routing."""

from __future__ import annotations

from uuid import uuid4

from src.api.control.study_agent.graph.graph import _route_after_study_agent
from src.api.control.study_agent.graph.resume_router import (
    hydrate_checkpoint_state,
    resolve_resume_next_node,
    route_after_study_agent,
)


def test_resolve_resume_after_concept_checklist_with_reference_goes_to_reference_router() -> (
    None
):
    state = {
        "generation_mode": "generate",
        "must_cover_checklist": [{"id": "c1", "concept": "loops"}],
        "has_reference_material": True,
        "reference_file_path": "/tmp/ref.pdf",
        "skip_llamaparse": False,
        "parsed_reference_data": {},
    }
    assert (
        resolve_resume_next_node(state, last_completed_node="concept_checklist")
        == "reference_router"
    )


def test_resolve_resume_after_reference_router_with_pdf_goes_to_llamaparse() -> None:
    state = {
        "generation_mode": "generate",
        "must_cover_checklist": [{"id": "c1", "concept": "loops"}],
        "has_reference_material": True,
        "reference_file_path": "/tmp/ref.pdf",
        "skip_llamaparse": False,
        "parsed_reference_data": {},
        "reference_mode": "pdf",
    }
    assert (
        resolve_resume_next_node(state, last_completed_node="reference_router")
        == "llamaparse"
    )


def test_resolve_resume_after_reference_router_external_goes_to_research() -> None:
    state = {
        "generation_mode": "generate",
        "must_cover_checklist": [{"id": "c1", "concept": "loops"}],
        "external_research_enabled": True,
        "reference_mode": "external",
    }
    assert (
        resolve_resume_next_node(state, last_completed_node="reference_router")
        == "external_research"
    )


def test_resolve_resume_after_reference_router_external_cache_hit_skips_research() -> (
    None
):
    state = {
        "generation_mode": "regenerate",
        "must_cover_checklist": [{"id": "c1", "concept": "loops"}],
        "reference_mode": "external",
        "external_research_cache_hit": True,
        "external_research_status": "success",
        "extracted_reference_text": "cached ground truth",
    }
    assert (
        resolve_resume_next_node(state, last_completed_node="reference_router")
        == "study_agent"
    )


def test_resolve_resume_after_external_research_goes_to_study_agent() -> None:
    state = {
        "generation_mode": "generate",
        "external_research_status": "success",
        "extracted_reference_text": "notes",
    }
    assert (
        resolve_resume_next_node(state, last_completed_node="external_research")
        == "study_agent"
    )


def test_resolve_resume_after_concept_checklist_without_reference_goes_to_reference_router() -> (
    None
):
    state = {
        "generation_mode": "generate",
        "must_cover_checklist": [{"id": "c1", "concept": "loops"}],
        "domain": "Programming",
    }
    assert (
        resolve_resume_next_node(state, last_completed_node="concept_checklist")
        == "reference_router"
    )


def test_resolve_resume_after_reference_router_none_goes_to_study_agent() -> None:
    state = {
        "generation_mode": "generate",
        "must_cover_checklist": [{"id": "c1", "concept": "loops"}],
        "domain": "Programming",
        "reference_mode": "none",
    }
    assert (
        resolve_resume_next_node(state, last_completed_node="reference_router")
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
        "generation_outcome": "study_document",
    }
    assert (
        resolve_resume_next_node(state, last_completed_node="study_agent")
        == "quality_check"
    )


def test_resolve_resume_after_study_agent_reference_required_ends() -> None:
    state = {
        "generated_content": '{"generation_status":"reference_required","message":"Upload a PDF"}',
        "generation_outcome": "reference_required",
    }
    assert (
        resolve_resume_next_node(state, last_completed_node="study_agent") == "__end__"
    )


def test_resolve_resume_after_study_agent_malformed_retries_generation() -> None:
    state = {
        "generated_content": '{"title":"broken"}',
        "generation_outcome": "malformed_document",
        "generator_format_attempt": 1,
    }
    assert (
        resolve_resume_next_node(state, last_completed_node="study_agent")
        == "study_agent"
    )


def test_route_after_study_agent_malformed_exhausted_ends() -> None:
    state = {
        "generation_outcome": "malformed_document",
        "generator_format_attempt": 3,
    }
    assert route_after_study_agent(state) == "__end__"
    assert _route_after_study_agent(state) == "__end__"


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


def test_resolve_resume_after_resolver_goes_to_concept_checklist() -> None:
    state = {
        "has_reference_material": True,
        "reference_file_path": "/tmp/ref.pdf",
        "skip_llamaparse": False,
    }
    assert (
        resolve_resume_next_node(state, last_completed_node="resolver")
        == "concept_checklist"
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
