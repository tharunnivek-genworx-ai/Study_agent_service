"""Tests for classify_generation_output and related outcome helpers."""

from __future__ import annotations

import json

import pytest

from src.api.utils.study_agent_utils.generation.generation_outcome_resolver import (
    map_graph_to_api,
    resolve_api_generation_outcome,
)
from src.api.utils.study_agent_utils.generation.study_generation_json import (
    build_action_required,
    classify_generation_output,
    render_outcome_content,
)

_STUDY_DOC = {
    "sections": [
        {
            "id": "mc_1",
            "heading": "Intro",
            "content": "Overview.",
        }
    ]
}

_REFERENCE_REQUIRED = {
    "generation_status": "reference_required",
    "topic_received": "Quantum computing",
    "reason": "Topic requires authoritative sources.",
    "message": "Upload a reference PDF to proceed.",
}

_VAGUE_IMPROVE = {
    "improve_status": "vague",
    "message": "IMPROVE STATUS: Feedback too vague to apply.",
}

_VAGUE_REGENERATE = {
    "regenerate_status": "vague",
    "message": "REGENERATE STATUS: Goal too vague to rewrite.",
}


class TestClassifyGenerationOutput:
    def test_study_document(self) -> None:
        raw = json.dumps(_STUDY_DOC)
        classified = classify_generation_output(raw)
        assert classified.outcome == "study_document"
        assert classified.document == _STUDY_DOC
        assert classified.detail == {}

    def test_reference_required(self) -> None:
        classified = classify_generation_output(json.dumps(_REFERENCE_REQUIRED))
        assert classified.outcome == "reference_required"
        assert classified.document == _REFERENCE_REQUIRED
        assert classified.detail["message"] == _REFERENCE_REQUIRED["message"]
        assert classified.detail["topic_received"] == "Quantum computing"

    def test_vague_improve_feedback(self) -> None:
        classified = classify_generation_output(json.dumps(_VAGUE_IMPROVE))
        assert classified.outcome == "vague_feedback"
        assert "vague" in classified.detail["message"].lower()

    def test_vague_regenerate_feedback(self) -> None:
        classified = classify_generation_output(json.dumps(_VAGUE_REGENERATE))
        assert classified.outcome == "vague_feedback"

    def test_malformed_document_not_status(self) -> None:
        raw = json.dumps({"title": "missing sections", "topic": "OOP"})
        classified = classify_generation_output(raw)
        assert classified.outcome == "malformed_document"
        assert classified.document is None
        assert classified.detail.get("raw_preview")
        assert classified.detail.get("reason")

    def test_generator_error_invalid_json(self) -> None:
        classified = classify_generation_output("not json at all")
        assert classified.outcome == "generator_error"
        assert classified.document is None
        assert classified.detail.get("reason")

    def test_strips_fenced_json_preamble(self) -> None:
        raw = f"Here is the document:\n```json\n{json.dumps(_STUDY_DOC)}\n```"
        classified = classify_generation_output(raw)
        assert classified.outcome == "study_document"
        assert classified.canonical_json.startswith('{"sections":')

    def test_malformed_sections_not_list(self) -> None:
        raw = json.dumps({"sections": "not-a-list"})
        classified = classify_generation_output(raw)
        assert classified.outcome == "malformed_document"


class TestRenderOutcomeContent:
    def test_malformed_persist_message(self) -> None:
        raw = json.dumps({"broken": True})
        classified = classify_generation_output(raw)
        content = render_outcome_content(
            classified.canonical_json,
            classified.outcome,
            classified.detail,
        )
        assert "GENERATION STATUS: Malformed document" in content
        assert "Preview:" in content

    def test_reference_required_renders_status_markdown(self) -> None:
        classified = classify_generation_output(json.dumps(_REFERENCE_REQUIRED))
        content = render_outcome_content(
            classified.canonical_json,
            classified.outcome,
            classified.detail,
        )
        assert "Reference material" in content or "Upload" in content


class TestBuildActionRequired:
    def test_upload_reference(self) -> None:
        action = build_action_required(
            "reference_required",
            {"message": "Upload a PDF.", "topic_received": "Rust"},
        )
        assert action is not None
        assert action.type == "upload_reference"
        assert action.topic_received == "Rust"

    def test_clarify_feedback(self) -> None:
        action = build_action_required(
            "vague_feedback",
            {"message": "Be more specific."},
        )
        assert action is not None
        assert action.type == "clarify_feedback"

    @pytest.mark.parametrize(
        "outcome",
        ["study_document", "malformed", "deliverable", "qc_failed"],
    )
    def test_no_action_for_other_outcomes(self, outcome: str) -> None:
        assert build_action_required(outcome, {}) is None


class TestResolveApiGenerationOutcome:
    def test_deliverable_after_qc_pass(self) -> None:
        outcome = resolve_api_generation_outcome(
            {
                "generation_outcome": "study_document",
                "qc_evaluated": True,
                "qc_passed": True,
            }
        )
        assert outcome == "deliverable"

    def test_qc_failed_after_qc_run(self) -> None:
        outcome = resolve_api_generation_outcome(
            {
                "generation_outcome": "study_document",
                "qc_evaluated": True,
                "qc_passed": False,
            }
        )
        assert outcome == "qc_failed"

    def test_malformed_graph_outcome_maps_to_api(self) -> None:
        assert map_graph_to_api("malformed_document") == "malformed"
        assert (
            resolve_api_generation_outcome({"generation_outcome": "malformed_document"})
            == "malformed"
        )
