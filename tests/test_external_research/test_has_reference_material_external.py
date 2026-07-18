"""Generator gate: external research text counts as reference material."""

from __future__ import annotations

from src.api.utils.study_agent_utils.graph.node_helpers import has_reference_material


def test_external_success_with_text_and_null_reference_material_id() -> None:
    """ER success + GT body must open the generator reference gate without a PDF id."""
    state = {
        "extracted_reference_text": "dense teaching-prep notes from external research",
        "reference_material_id": None,
        "has_reference_material": False,
        "reference_mode": "external",
        "external_research_status": "success",
    }
    assert has_reference_material(state) is True


def test_external_mode_with_text_without_status_flag() -> None:
    state = {
        "extracted_reference_text": "cached ground truth notebook",
        "reference_material_id": None,
        "has_reference_material": False,
        "reference_mode": "external",
    }
    assert has_reference_material(state) is True


def test_external_success_status_with_text_without_mode() -> None:
    state = {
        "extracted_reference_text": "merged notes",
        "reference_material_id": None,
        "has_reference_material": False,
        "external_research_status": "success",
    }
    assert has_reference_material(state) is True


def test_external_empty_text_is_not_reference() -> None:
    state = {
        "extracted_reference_text": "",
        "reference_material_id": None,
        "has_reference_material": False,
        "reference_mode": "external",
        "external_research_status": "success",
    }
    assert has_reference_material(state) is False


def test_none_mode_with_text_but_no_pdf_or_er_flag_is_not_reference() -> None:
    """Avoid treating stray text as reference when mode is none and ER did not succeed."""
    state = {
        "extracted_reference_text": "some leftover text",
        "reference_material_id": None,
        "has_reference_material": False,
        "reference_mode": "none",
        "external_research_status": "fail_soft",
    }
    assert has_reference_material(state) is False


def test_pdf_id_with_text_still_counts() -> None:
    state = {
        "extracted_reference_text": "parsed pdf body",
        "reference_material_id": "00000000-0000-0000-0000-000000000001",
        "has_reference_material": False,
        "reference_mode": "pdf",
    }
    assert has_reference_material(state) is True
