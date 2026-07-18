"""Graph routing tests for external research → checklist_realign."""

from __future__ import annotations

from src.api.control.study_agent.graph.graph import (
    _route_after_checklist_realign,
    _route_after_external_research,
    _route_after_reference_router,
)
from src.api.control.study_agent.nodes.external_research_node import _RESULT_KEYS


def test_route_after_external_research_success_goes_to_realign() -> None:
    assert (
        _route_after_external_research(
            {"external_research_status": "success", "extracted_reference_text": "gt"}
        )
        == "checklist_realign"
    )


def test_route_after_external_research_error_ends() -> None:
    assert _route_after_external_research({"error": "subgraph crashed"}) == "__end__"


def test_route_after_reference_router_cache_hit_goes_to_realign() -> None:
    state = {
        "external_research_enabled": True,
        "reference_mode": "external",
        "external_research_cache_hit": True,
        "external_research_status": "success",
        "extracted_reference_text": "cached",
    }
    assert _route_after_reference_router(state) == "checklist_realign"


def test_route_after_reference_router_external_fresh_goes_to_research() -> None:
    state = {
        "external_research_enabled": True,
        "reference_mode": "external",
    }
    assert _route_after_reference_router(state) == "external_research"


def test_route_after_reference_router_pdf_goes_to_llamaparse() -> None:
    state = {
        "reference_mode": "pdf",
        "has_reference_material": True,
        "reference_file_path": "/tmp/ref.pdf",
        "skip_llamaparse": False,
        "parsed_reference_data": {},
    }
    assert _route_after_reference_router(state) == "llamaparse"


def test_route_after_reference_router_none_goes_to_study_agent() -> None:
    state = {"reference_mode": "none"}
    assert _route_after_reference_router(state) == "study_agent"


def test_route_after_checklist_realign_goes_to_study_agent() -> None:
    assert _route_after_checklist_realign({}) == "study_agent"


def test_external_research_result_keys_include_has_reference_material() -> None:
    assert "has_reference_material" in _RESULT_KEYS
