# tests/test_document_merge.py
"""Unit tests for document_merge utilities."""

from __future__ import annotations

from src.api.utils.study_agent_utils.quality_check_utils.document.document_merge import (
    build_document_outline,
    extract_sections_by_ids,
    insert_sections,
    merge_full_regeneration_preserving_passing,
    merge_section_field_patches,
    merge_section_patches,
    merge_section_patches_scoped,
)


def _doc(*sections: dict) -> dict:
    return {"sections": list(sections)}


class TestMergeSectionPatches:
    def test_replaces_sections_by_id(self):
        document = _doc(
            {"id": "mc_1", "heading": "Intro", "content": "old intro"},
            {"id": "mc_2", "heading": "Examples", "content": "old examples"},
        )
        patches = [
            {"id": "mc_2", "heading": "Examples", "content": "new examples"},
        ]

        result = merge_section_patches(document, patches)

        assert result.unmatched_patch_ids == []
        assert result.document["sections"][0]["content"] == "old intro"
        assert result.document["sections"][1]["content"] == "new examples"
        assert document["sections"][1]["content"] == "old examples"

    def test_reports_unmatched_patch_ids(self):
        document = _doc({"id": "mc_1", "heading": "Intro", "content": "intro"})
        patches = [
            {"id": "mc_9", "heading": "Missing", "content": "never merged"},
        ]

        result = merge_section_patches(document, patches)

        assert result.unmatched_patch_ids == ["mc_9"]
        assert len(result.document["sections"]) == 1

    def test_skips_patches_without_id(self):
        document = _doc({"id": "mc_1", "heading": "Intro", "content": "intro"})
        result = merge_section_patches(document, [{"heading": "No id", "content": "x"}])
        assert result.unmatched_patch_ids == []
        assert result.document["sections"][0]["content"] == "intro"


class TestMergeSectionFieldPatches:
    def test_updates_only_block_fields_preserving_subsections(self):
        document = _doc(
            {
                "id": "ts_2",
                "heading": "Derivatives",
                "content": "old prose with inline math",
                "subsections": [
                    {
                        "heading": "Examples",
                        "content": "untouched subsection prose",
                    }
                ],
            }
        )
        patches = [
            {
                "id": "ts_2",
                "heading": "Renamed heading",
                "content": "relocated prose only",
                "formula_blocks": [
                    {
                        "notation": "plain-text",
                        "formula": "f'(x) = ...",
                        "explanation": "Relocated equation.",
                    }
                ],
            }
        ]

        result = merge_section_field_patches(document, patches)

        section = result.document["sections"][0]
        assert section["heading"] == "Derivatives"
        assert section["content"] == "relocated prose only"
        assert section["formula_blocks"][0]["formula"] == "f'(x) = ..."
        assert section["subsections"][0]["content"] == "untouched subsection prose"

    def test_merges_subsection_block_fields_by_heading(self):
        document = _doc(
            {
                "id": "ts_2",
                "heading": "Derivatives",
                "content": "section prose",
                "subsections": [
                    {
                        "heading": "Examples",
                        "content": "inline if f(x) = x^2 then f'(x) = 2x",
                        "formula_blocks": [],
                    }
                ],
            }
        )
        patches = [
            {
                "id": "ts_2",
                "content": "section prose",
                "subsections": [
                    {
                        "heading": "Examples",
                        "content": "relocated subsection prose",
                        "formula_blocks": [
                            {
                                "notation": "plain-text",
                                "formula": "f'(x) = 2x",
                                "explanation": "Power rule example.",
                            }
                        ],
                    }
                ],
            }
        ]

        result = merge_section_field_patches(document, patches)

        subsection = result.document["sections"][0]["subsections"][0]
        assert subsection["content"] == "relocated subsection prose"
        assert subsection["formula_blocks"][0]["formula"] == "f'(x) = 2x"
        assert result.document["sections"][0]["heading"] == "Derivatives"


class TestMergeSectionPatchesScoped:
    def test_restores_untargeted_subsections_after_patch(self):
        document = _doc(
            {
                "id": "ts_2",
                "heading": "Rules",
                "content": "stable section prose",
                "subsections": [
                    {"heading": "Intro", "content": "stable intro"},
                    {"heading": "Examples", "content": "bad inline math"},
                    {"heading": "Summary", "content": "stable summary"},
                ],
            }
        )
        patches = [
            {
                "id": "ts_2",
                "heading": "Rules",
                "content": "rewritten section prose",
                "subsections": [
                    {"heading": "Intro", "content": "accidentally rewritten intro"},
                    {
                        "heading": "Examples",
                        "content": "fixed prose only",
                        "formula_blocks": [
                            {
                                "notation": "plain-text",
                                "formula": "f'(x)=2x",
                                "explanation": "Power rule.",
                            }
                        ],
                    },
                    {"heading": "Summary", "content": "accidentally rewritten summary"},
                ],
            }
        ]
        section_failures = [
            {
                "section_id": "ts_2",
                "failures": [
                    {
                        "category": "document_coherence",
                        "evidence": (
                            "Section 'Rules', subsection 'Examples': "
                            "Prose contains display-math patterns"
                        ),
                        "corrective_hint": "Move equations into formula_blocks.",
                    }
                ],
            }
        ]

        result = merge_section_patches_scoped(
            document,
            patches,
            section_failures=section_failures,
        )

        section = result.document["sections"][0]
        assert section["content"] == "stable section prose"
        subsections = {
            item["heading"]: item["content"] for item in section["subsections"]
        }
        assert subsections["Intro"] == "stable intro"
        assert subsections["Examples"] == "fixed prose only"
        assert subsections["Summary"] == "stable summary"

    def test_falls_back_to_full_patch_without_subsection_targets(self):
        document = _doc(
            {
                "id": "ts_2",
                "heading": "Rules",
                "content": "old section prose",
                "subsections": [{"heading": "Intro", "content": "old intro"}],
            }
        )
        patches = [
            {
                "id": "ts_2",
                "heading": "Rules",
                "content": "new section prose",
                "subsections": [{"heading": "Intro", "content": "new intro"}],
            }
        ]
        section_failures = [
            {
                "section_id": "ts_2",
                "failures": [
                    {
                        "category": "content_accuracy",
                        "evidence": "Section 'Rules': incoherent flow throughout.",
                        "corrective_hint": "Rewrite the entire section.",
                    }
                ],
            }
        ]

        result = merge_section_patches_scoped(
            document,
            patches,
            section_failures=section_failures,
        )

        section = result.document["sections"][0]
        assert section["content"] == "new section prose"
        assert section["subsections"][0]["content"] == "new intro"


class TestInsertSections:
    def test_inserts_after_lower_checklist_order(self):
        document = _doc(
            {"id": "mc_1", "heading": "Intro", "content": "intro"},
            {"id": "mc_3", "heading": "Advanced", "content": "advanced"},
        )
        new_sections = [
            {"id": "mc_2", "heading": "Basics", "content": "basics"},
        ]

        merged = insert_sections(document, new_sections)

        ids = [section["id"] for section in merged["sections"]]
        assert ids == ["mc_1", "mc_2", "mc_3"]

    def test_appends_when_no_lower_order_section_exists(self):
        document = _doc({"id": "mc_5", "heading": "Later", "content": "later"})
        merged = insert_sections(
            document,
            [{"id": "mc_8", "heading": "New", "content": "new"}],
        )
        ids = [section["id"] for section in merged["sections"]]
        assert ids == ["mc_5", "mc_8"]

    def test_inserts_multiple_sections_in_checklist_order(self):
        document = _doc({"id": "mc_1", "heading": "Intro", "content": "intro"})
        merged = insert_sections(
            document,
            [
                {"id": "mc_4", "heading": "Four", "content": "four"},
                {"id": "mc_2", "heading": "Two", "content": "two"},
            ],
        )
        ids = [section["id"] for section in merged["sections"]]
        assert ids == ["mc_1", "mc_2", "mc_4"]

    def test_after_section_id_overrides_default_position(self):
        document = _doc(
            {"id": "mc_1", "heading": "Intro", "content": "intro"},
            {"id": "mc_3", "heading": "Advanced", "content": "advanced"},
        )
        merged = insert_sections(
            document,
            [{"id": "mc_2", "heading": "Basics", "content": "basics"}],
            after_section_id="mc_3",
        )
        ids = [section["id"] for section in merged["sections"]]
        assert ids == ["mc_1", "mc_3", "mc_2"]

    def test_skips_duplicate_section_ids(self):
        document = _doc({"id": "mc_1", "heading": "Intro", "content": "intro"})
        merged = insert_sections(
            document,
            [{"id": "mc_1", "heading": "Duplicate", "content": "dup"}],
        )
        assert len(merged["sections"]) == 1
        assert merged["sections"][0]["content"] == "intro"


class TestExtractSectionsByIds:
    def test_returns_sections_in_requested_order(self):
        document = _doc(
            {"id": "mc_1", "heading": "Intro", "content": "intro"},
            {"id": "mc_2", "heading": "Examples", "content": "examples"},
        )
        extracted = extract_sections_by_ids(document, ["mc_2", "mc_1"])
        assert [section["id"] for section in extracted] == ["mc_2", "mc_1"]
        assert extracted[0]["content"] == "examples"

    def test_omits_unknown_ids(self):
        document = _doc({"id": "mc_1", "heading": "Intro", "content": "intro"})
        extracted = extract_sections_by_ids(document, ["mc_9"])
        assert extracted == []


class TestBuildDocumentOutline:
    def test_lists_ids_and_headings(self):
        document = _doc(
            {"id": "mc_1", "heading": "Introduction", "content": "intro"},
            {"id": "mc_2", "heading": "Examples", "content": "examples"},
        )
        outline = build_document_outline(document)
        assert outline == "- [mc_1] Introduction\n- [mc_2] Examples"


class TestMergeFullRegenerationPreservingPassing:
    def test_preserves_passing_sections_from_previous_draft(self):
        previous = _doc(
            {"id": "ts_1", "heading": "Intro", "content": "stable intro"},
            {"id": "ts_2", "heading": "Classes", "content": "stable classes"},
            {"id": "ts_7", "heading": "Pitfalls", "content": "stable pitfalls"},
        )
        new = _doc(
            {"id": "ts_1", "heading": "Intro", "content": "rewritten intro"},
            {"id": "ts_2", "heading": "Classes", "content": "rewritten classes"},
        )
        topic_split = [
            {"id": "ts_1", "heading": "Intro"},
            {"id": "ts_2", "heading": "Classes"},
            {"id": "ts_7", "heading": "Pitfalls"},
        ]

        merged = merge_full_regeneration_preserving_passing(
            new,
            previous,
            rewrite_section_ids={"ts_1", "ts_2"},
            topic_split=topic_split,
        )

        by_id = {section["id"]: section["content"] for section in merged["sections"]}
        assert by_id["ts_1"] == "rewritten intro"
        assert by_id["ts_2"] == "rewritten classes"
        assert by_id["ts_7"] == "stable pitfalls"
        assert [section["id"] for section in merged["sections"]] == [
            "ts_1",
            "ts_2",
            "ts_7",
        ]
