"""Tests for external generator addenda, reference_kind, and user-block tags."""

from __future__ import annotations

import pytest

from src.api.control.study_agent.prompts.generation import generation_prompt
from src.api.control.study_agent.prompts.generation.external import (
    EXTERNAL_ADDENDA_BY_DOMAIN,
    EXTERNAL_ADDENDUM_CONCEPTUAL,
    EXTERNAL_ADDENDUM_MIXED,
    EXTERNAL_ADDENDUM_PROGRAMMING,
    EXTERNAL_ADDENDUM_STEM,
    SHARED_EXTERNAL_POLICY,
    resolve_external_addendum,
)
from src.api.utils.study_agent_utils.graph.node_helpers import reference_kind

_PDF_IMAGE_ANCHOR = "[IMAGE:"
_POLICY_KEYWORDS = (
    "research_notes",
    "adapt",
    "invent",
    "do not dump",
    "topic_split",
)


@pytest.mark.parametrize(
    ("domain", "expected"),
    [
        ("STEM", EXTERNAL_ADDENDUM_STEM),
        ("Programming", EXTERNAL_ADDENDUM_PROGRAMMING),
        ("Conceptual", EXTERNAL_ADDENDUM_CONCEPTUAL),
        ("Mixed", EXTERNAL_ADDENDUM_MIXED),
    ],
)
def test_resolve_external_addendum_by_domain(domain: str, expected: str) -> None:
    assert resolve_external_addendum(domain) == expected


@pytest.mark.parametrize("domain", [None, "", "UnknownDomain", "Biology"])
def test_resolve_external_addendum_falls_back_to_mixed(domain: str | None) -> None:
    assert resolve_external_addendum(domain) == EXTERNAL_ADDENDUM_MIXED


def test_external_addenda_map_covers_four_domains() -> None:
    assert set(EXTERNAL_ADDENDA_BY_DOMAIN) == {
        "STEM",
        "Programming",
        "Conceptual",
        "Mixed",
    }


def test_shared_policy_has_gt_first_invent_for_gaps_no_paste_keywords() -> None:
    lower = SHARED_EXTERNAL_POLICY.lower()
    for keyword in _POLICY_KEYWORDS:
        assert keyword in lower, f"missing policy keyword: {keyword}"
    assert "prefer them as ground truth" in lower or "ground truth" in lower
    assert "notes omit" in lower or "lack that concept" in lower


def test_domain_addenda_include_shared_policy() -> None:
    for addendum in EXTERNAL_ADDENDA_BY_DOMAIN.values():
        assert SHARED_EXTERNAL_POLICY in addendum


def test_reference_kind_none_without_material() -> None:
    assert (
        reference_kind(
            {
                "extracted_reference_text": "",
                "reference_mode": "external",
            }
        )
        == "none"
    )


def test_reference_kind_external_when_mode_and_text() -> None:
    assert (
        reference_kind(
            {
                "extracted_reference_text": "dense GT notes",
                "reference_mode": "external",
                "reference_material_id": None,
                "has_reference_material": False,
            }
        )
        == "external"
    )


def test_reference_kind_pdf_when_pdf_text_present() -> None:
    assert (
        reference_kind(
            {
                "extracted_reference_text": "parsed pdf body",
                "reference_mode": "pdf",
                "reference_material_id": "00000000-0000-0000-0000-000000000001",
            }
        )
        == "pdf"
    )


def test_reference_kind_pdf_default_when_material_without_external_mode() -> None:
    assert (
        reference_kind(
            {
                "extracted_reference_text": "some pdf text",
                "reference_material_id": "00000000-0000-0000-0000-000000000001",
                "reference_mode": "none",
            }
        )
        == "pdf"
    )


def test_format_reference_user_block_external_uses_research_notes() -> None:
    block = generation_prompt.format_reference_user_block(
        "GT notebook body",
        has_reference=True,
        reference_kind="external",
    )
    assert "<research_notes>" in block
    assert "</research_notes>" in block
    assert "<reference_material>" not in block
    assert "GT notebook body" in block


def test_format_reference_user_block_pdf_uses_reference_material() -> None:
    block = generation_prompt.format_reference_user_block(
        "PDF excerpt",
        has_reference=True,
        reference_kind="pdf",
    )
    assert "<reference_material>" in block
    assert "</reference_material>" in block
    assert "<research_notes>" not in block


def test_format_reference_user_block_legacy_has_reference_defaults_to_pdf_tag() -> None:
    block = generation_prompt.format_reference_user_block(
        "legacy text",
        has_reference=True,
    )
    assert "<reference_material>" in block


@pytest.mark.parametrize(
    "domain",
    ["STEM", "Programming", "Conceptual", "Mixed"],
)
def test_build_system_prompt_external_includes_addendum_excludes_pdf_image(
    domain: str,
) -> None:
    prompt = generation_prompt.build_system_prompt(
        has_reference=True,
        domain=domain,
        reference_kind="external",
    )
    expected = resolve_external_addendum(domain)
    assert expected in prompt
    assert _PDF_IMAGE_ANCHOR not in prompt
    assert "EXTERNAL RESEARCH NOTES POLICY" in prompt


def test_build_system_prompt_pdf_has_reference_keeps_image_rule() -> None:
    prompt = generation_prompt.build_system_prompt(
        has_reference=True,
        domain="Programming",
        reference_kind="pdf",
    )
    assert _PDF_IMAGE_ANCHOR in prompt
    assert "EXTERNAL RESEARCH NOTES POLICY" not in prompt


def test_build_system_prompt_legacy_has_reference_true_keeps_pdf_addendum() -> None:
    """Default reference_kind keeps PDF snapshots/behavior stable."""
    prompt = generation_prompt.build_system_prompt(
        has_reference=True,
        domain="",
    )
    assert _PDF_IMAGE_ANCHOR in prompt
    assert "EXTERNAL RESEARCH NOTES POLICY" not in prompt
