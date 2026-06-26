# tests/test_topic_split_scoping.py
"""Unit tests for scoped topic_split filtering in surgical retries."""

from __future__ import annotations

from src.api.utils.study_agent_utils.graph import node_helpers as helpers

_TOPIC_SPLIT = [
    {
        "id": "ts_1",
        "heading": "Overview",
        "purpose": "Introduce the topic",
        "depth": "brief",
        "min_words": 150,
        "min_examples": 1,
    },
    {
        "id": "ts_2",
        "heading": "Inheritance",
        "purpose": "Explain inheritance types",
        "depth": "deep",
        "min_words": 700,
        "min_examples": 3,
        "coverage_notes": "Cover single, multilevel, hierarchical",
    },
    {
        "id": "ts_3",
        "heading": "Polymorphism",
        "purpose": "Runtime polymorphism",
        "depth": "medium",
        "min_words": 350,
        "min_examples": 2,
    },
]

_CHECKLIST = [
    {
        "id": "mc_1",
        "concept": "Overview",
        "requirement": "Define the topic",
        "priority": "required",
        "section_id": "ts_1",
    },
    {
        "id": "mc_2",
        "concept": "Inheritance",
        "requirement": "Show all inheritance types",
        "priority": "required",
        "section_id": "ts_2",
    },
    {
        "id": "mc_3",
        "concept": "Polymorphism",
        "requirement": "Demonstrate runtime polymorphism",
        "priority": "required",
        "section_id": "ts_3",
    },
]


class TestTopicSplitForTargets:
    def test_filters_by_section_ids_for_patch(self):
        scoped = helpers.topic_split_for_targets(
            _TOPIC_SPLIT,
            section_ids=["ts_2"],
            checklist=_CHECKLIST,
        )
        assert [entry["id"] for entry in scoped] == ["ts_2"]

    def test_resolves_missing_checklist_id_to_section_id_for_insert(self):
        scoped = helpers.topic_split_for_targets(
            _TOPIC_SPLIT,
            missing_checklist_ids=["mc_3"],
            checklist=_CHECKLIST,
        )
        assert [entry["id"] for entry in scoped] == ["ts_3"]

    def test_includes_direct_topic_split_missing_id(self):
        scoped = helpers.topic_split_for_targets(
            _TOPIC_SPLIT,
            missing_checklist_ids=["ts_2"],
            checklist=_CHECKLIST,
        )
        assert [entry["id"] for entry in scoped] == ["ts_2"]

    def test_unions_patch_and_insert_targets(self):
        scoped = helpers.topic_split_for_targets(
            _TOPIC_SPLIT,
            section_ids=["ts_1"],
            missing_checklist_ids=["mc_3"],
            checklist=_CHECKLIST,
        )
        assert [entry["id"] for entry in scoped] == ["ts_1", "ts_3"]

    def test_returns_empty_when_no_targets_match(self):
        scoped = helpers.topic_split_for_targets(
            _TOPIC_SPLIT,
            section_ids=["ts_missing"],
            checklist=_CHECKLIST,
        )
        assert scoped == []


class TestBuildScopedTopicSplitBlock:
    def test_includes_only_target_sections(self):
        state = {
            "topic_split": _TOPIC_SPLIT,
            "must_cover_checklist": _CHECKLIST,
        }
        block = helpers.build_scoped_topic_split_block(
            state,
            section_ids=["ts_2"],
        )
        assert "ts_2" in block
        assert "Inheritance" in block
        assert "Explain inheritance types" in block
        assert "ts_1" not in block
        assert "ts_3" not in block

    def test_returns_empty_string_when_nothing_in_scope(self):
        state = {
            "topic_split": _TOPIC_SPLIT,
            "must_cover_checklist": _CHECKLIST,
        }
        assert (
            helpers.build_scoped_topic_split_block(state, section_ids=["ts_missing"])
            == ""
        )


class TestSectionIdsFromFailures:
    def test_extracts_section_ids(self):
        failures = [
            {"section_id": "ts_2", "heading": "Inheritance", "failures": []},
            {"section_id": "", "heading": "skip"},
            {"section_id": "ts_3", "failures": []},
        ]
        assert helpers.section_ids_from_failures(failures) == ["ts_2", "ts_3"]


class TestChecklistForReverify:
    def test_scopes_by_canonical_section_id_not_checklist_id_collision(self):
        scoped = helpers.checklist_for_reverify(
            _CHECKLIST,
            section_ids=["ts_2"],
            missing_checklist_ids=[],
        )
        assert [item["id"] for item in scoped] == ["mc_2"]

    def test_includes_missing_checklist_ids(self):
        scoped = helpers.checklist_for_reverify(
            _CHECKLIST,
            section_ids=[],
            missing_checklist_ids=["mc_3"],
        )
        assert [item["id"] for item in scoped] == ["mc_3"]
