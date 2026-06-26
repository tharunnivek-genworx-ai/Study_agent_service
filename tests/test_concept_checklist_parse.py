# tests/test_concept_checklist_parse.py
"""Unit tests for concept checklist parsing (topic_split + must_cover)."""

from __future__ import annotations

import json

from src.api.schemas.study_material_schemas.concept_checklist_schema import (
    parse_concept_checklist_response,
)


class TestParseConceptChecklistResponse:
    def test_parses_object_with_topic_split_and_checklist(self):
        raw = json.dumps(
            {
                "domain": "Programming",
                "topic_split": [
                    {
                        "id": "ts_1",
                        "heading": "Intro",
                        "purpose": "Define the topic",
                    }
                ],
                "must_cover_checklist": [
                    {
                        "id": "mc_1",
                        "concept": "Intro",
                        "requirement": "Define the topic",
                        "priority": "required",
                        "section_id": "ts_1",
                        "depth_gate": "Concept defined with a runnable example.",
                    }
                ],
            }
        )
        parsed = parse_concept_checklist_response(raw)
        assert parsed is not None
        assert parsed.domain == "Programming"
        assert len(parsed.topic_split) == 1
        assert parsed.topic_split[0].id == "ts_1"
        assert "depth" not in parsed.topic_split[0].model_dump()
        assert parsed.must_cover_checklist[0].section_id == "ts_1"
        assert parsed.must_cover_checklist[0].depth_gate == (
            "Concept defined with a runnable example."
        )

    def test_parses_legacy_array_only(self):
        raw = json.dumps(
            [
                {
                    "id": "mc_1",
                    "concept": "Core",
                    "requirement": "Explain core ideas",
                    "priority": "required",
                }
            ]
        )
        parsed = parse_concept_checklist_response(raw)
        assert parsed is not None
        assert parsed.must_cover_checklist[0].id == "mc_1"
        assert parsed.topic_split[0].id == "mc_1"
