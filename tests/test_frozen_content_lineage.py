# tests/test_frozen_content_lineage.py
"""Unit tests for frozen-set content lineage helpers."""

from __future__ import annotations

import json
from types import SimpleNamespace

from src.api.core.services.study_agent_services.study_material_service import (
    _hydration_from_active_version,
)
from src.api.utils.study_agent_utils.quality_check_utils.core.frozen_sets import (
    build_section_hashes,
    effective_frozen_sets,
    hash_section,
    prune_frozen_for_sections,
    refresh_frozen_lineage_after_qc,
    resolve_frozen_for_full_qc,
)

_SAMPLE_DOC = {
    "sections": [
        {"id": "s1", "heading": "Intro", "content": "Intro only."},
        {
            "id": "s2",
            "heading": "Examples",
            "content": "Example prose.",
            "code_blocks": [{"language": "python", "code": "pass"}],
        },
    ]
}

_CHECKLIST = [
    {"id": "mc_1", "section_id": "s1", "concept": "Intro", "priority": "required"},
    {"id": "mc_2", "section_id": "s2", "concept": "Examples", "priority": "required"},
]


class TestHashSection:
    def test_stable_for_same_content(self):
        section = {"id": "s1", "heading": "A", "content": "text"}
        assert hash_section(section) == hash_section(dict(section))

    def test_changes_when_content_changes(self):
        a = {"id": "s1", "heading": "A", "content": "text"}
        b = {"id": "s1", "heading": "A", "content": "other"}
        assert hash_section(a) != hash_section(b)


class TestBuildSectionHashes:
    def test_maps_all_section_ids(self):
        hashes = build_section_hashes(_SAMPLE_DOC)
        assert set(hashes) == {"s1", "s2"}
        assert hashes["s1"] == hash_section(_SAMPLE_DOC["sections"][0])


class TestPruneFrozenForSections:
    def test_drops_touched_section_and_mapped_checklist_ids(self):
        check_ids, section_ids = prune_frozen_for_sections(
            ["mc_1", "mc_2"],
            ["s1", "s2"],
            touched_section_ids={"s2"},
            checklist=_CHECKLIST,
        )
        assert check_ids == ["mc_1"]
        assert section_ids == ["s1"]

    def test_drops_explicit_reverify_checklist_ids(self):
        check_ids, section_ids = prune_frozen_for_sections(
            ["mc_1", "mc_4"],
            ["s1"],
            touched_section_ids=set(),
            reverify_checklist_ids={"mc_4"},
        )
        assert check_ids == ["mc_1"]
        assert section_ids == ["s1"]


class TestEffectiveFrozenSets:
    def test_returns_empty_when_no_stored_hashes(self):
        check_ids, section_ids = effective_frozen_sets(
            frozen_check_ids=["mc_1"],
            frozen_section_ids=["s1"],
            stored_hashes=None,
            document=_SAMPLE_DOC,
            checklist=_CHECKLIST,
        )
        assert check_ids == []
        assert section_ids == []

    def test_keeps_ids_when_content_unchanged(self):
        stored = build_section_hashes(_SAMPLE_DOC)
        check_ids, section_ids = effective_frozen_sets(
            frozen_check_ids=["mc_1", "mc_2"],
            frozen_section_ids=["s1", "s2"],
            stored_hashes=stored,
            document=_SAMPLE_DOC,
            checklist=_CHECKLIST,
        )
        assert check_ids == ["mc_1", "mc_2"]
        assert section_ids == ["s1", "s2"]

    def test_drops_ids_when_section_content_changed(self):
        stored = build_section_hashes(_SAMPLE_DOC)
        changed_doc = {
            "sections": [
                _SAMPLE_DOC["sections"][0],
                {**_SAMPLE_DOC["sections"][1], "content": "Rewritten."},
            ]
        }
        check_ids, section_ids = effective_frozen_sets(
            frozen_check_ids=["mc_1", "mc_2"],
            frozen_section_ids=["s1", "s2"],
            stored_hashes=stored,
            document=changed_doc,
            checklist=_CHECKLIST,
        )
        assert check_ids == ["mc_1"]
        assert section_ids == ["s1"]

    def test_resolve_alias_matches_effective(self):
        stored = build_section_hashes(_SAMPLE_DOC)
        assert resolve_frozen_for_full_qc(
            frozen_check_ids=["mc_1"],
            frozen_section_ids=["s1"],
            stored_hashes=stored,
            document=_SAMPLE_DOC,
            checklist=_CHECKLIST,
        ) == effective_frozen_sets(
            frozen_check_ids=["mc_1"],
            frozen_section_ids=["s1"],
            stored_hashes=stored,
            document=_SAMPLE_DOC,
            checklist=_CHECKLIST,
        )


class TestRefreshFrozenLineageAfterQc:
    def test_full_qc_accumulates_and_refreshes_hashes(self):
        checks = [
            {"category": "must_cover", "passed": True, "checklist_id": "mc_1"},
            {"category": "code_quality", "passed": True, "section_id": "s2"},
        ]
        check_ids, section_ids, hashes = refresh_frozen_lineage_after_qc(
            checks,
            existing_check_ids=["mc_2"],
            existing_section_ids=[],
            document=_SAMPLE_DOC,
        )
        assert check_ids == ["mc_1", "mc_2"]
        assert section_ids == ["s2"]
        assert hashes == build_section_hashes(_SAMPLE_DOC)

    def test_targeted_qc_prunes_before_accumulate(self):
        checks = [
            {"category": "must_cover", "passed": True, "checklist_id": "mc_2"},
            {"category": "code_quality", "passed": True, "section_id": "s2"},
        ]
        check_ids, section_ids, hashes = refresh_frozen_lineage_after_qc(
            checks,
            existing_check_ids=["mc_1", "mc_2"],
            existing_section_ids=["s1", "s2"],
            document=_SAMPLE_DOC,
            checklist=_CHECKLIST,
            touched_section_ids=["s2"],
        )
        assert check_ids == ["mc_1", "mc_2"]
        assert section_ids == ["s1", "s2"]
        assert hashes == build_section_hashes(_SAMPLE_DOC)


class TestHydrationGate:
    def test_resume_hydration_matches_effective_frozen_sets(self):
        stored = build_section_hashes(_SAMPLE_DOC)
        changed_doc = {
            "sections": [
                _SAMPLE_DOC["sections"][0],
                {**_SAMPLE_DOC["sections"][1], "content": "Rewritten."},
            ]
        }
        active = SimpleNamespace(
            content=json.dumps(changed_doc),
            concept_plan={"must_cover_checklist": _CHECKLIST},
            qc_frozen_check_ids=["mc_1", "mc_2"],
            qc_frozen_section_keys=["s1", "s2"],
            qc_section_content_hashes=stored,
            qc_result=None,
        )

        hydration, _ = _hydration_from_active_version(active)
        expected_check_ids, expected_section_ids = effective_frozen_sets(
            frozen_check_ids=["mc_1", "mc_2"],
            frozen_section_ids=["s1", "s2"],
            stored_hashes=stored,
            document=changed_doc,
            checklist=_CHECKLIST,
        )

        assert hydration.get("qc_frozen_check_ids") == expected_check_ids
        assert hydration.get("qc_frozen_section_keys") == expected_section_ids
        assert hydration["qc_section_content_hashes"] == stored
