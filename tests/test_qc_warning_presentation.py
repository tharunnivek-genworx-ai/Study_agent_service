"""Tests for mentor-facing QC warning presentation builders."""

from __future__ import annotations

from src.api.utils.study_agent_utils.quality_check_utils.results.warning_presentation import (
    build_qc_warning_presentation,
    enrich_qc_result_for_client,
    extract_failed_checks,
)

CONCEPT_PLAN = {
    "domain": "STEM",
    "topic_split": [
        {"id": "ts_1", "heading": "Introduction to Limits"},
        {"id": "ts_3", "heading": "Derivation of the Power Rule"},
    ],
}


def _qc_with_failed_checks(failed: list[dict], **extra) -> dict:
    return {
        "overall_status": "fail",
        "is_refusal": False,
        "hallucination_risk": "none",
        "scores": {
            "content_accuracy": 10,
            "section_depth": 9,
            "teaching_alignment": 10,
        },
        "checks": [
            *[{**check, "passed": False} for check in failed],
            {
                "id": "mc_1",
                "category": "must_cover",
                "question": "Coverage ok",
                "passed": True,
                "severity": "critical",
            },
        ],
        "issues": [],
        "corrective_instructions": "",
        "summary": "",
        **extra,
    }


def test_extract_failed_checks_from_checks_array() -> None:
    qc = _qc_with_failed_checks(
        [
            {
                "id": "det_equation_in_content",
                "category": "document_coherence",
                "question": "q",
                "severity": "critical",
                "section_id": "ts_3",
                "evidence": (
                    "Section 'Derivation of the Power Rule': "
                    "Prose contains display-math patterns"
                ),
            }
        ]
    )
    failed = extract_failed_checks(qc)
    assert len(failed) == 1
    assert failed[0]["id"] == "det_equation_in_content"


def test_extract_failed_checks_falls_back_to_failed_checks() -> None:
    qc = {
        "overall_status": "fail",
        "checks": [],
        "failed_checks": [
            {
                "id": "det_equation_in_content",
                "passed": False,
                "severity": "critical",
                "section_id": "ts_3",
            }
        ],
    }
    failed = extract_failed_checks(qc)
    assert len(failed) == 1


def test_det_only_formatting_presentation() -> None:
    qc = _qc_with_failed_checks(
        [
            {
                "id": "det_equation_in_content",
                "category": "document_coherence",
                "question": "Are equations stored in formula_blocks?",
                "severity": "critical",
                "section_id": "ts_3",
                "evidence": (
                    "Section 'Derivation of the Power Rule': "
                    "Prose contains display-math patterns"
                ),
                "corrective_hint": "Move equations into formula_blocks.",
            }
        ]
    )
    presentation = build_qc_warning_presentation(qc, CONCEPT_PLAN)
    assert presentation is not None
    assert presentation["kind"] == "det_only"
    assert presentation["alert_title"] == "Document formatting note"
    assert len(presentation["formatting_items"]) == 1
    assert (
        "Derivation of the Power Rule"
        in presentation["formatting_items"][0]["user_message"]
    )
    assert presentation["reassurance"]
    assert presentation["det_summary"] and "1 item" in presentation["det_summary"]


def test_mixed_det_and_llm_presentation() -> None:
    qc = _qc_with_failed_checks(
        [
            {
                "id": "det_equation_in_content",
                "category": "document_coherence",
                "question": "q",
                "severity": "critical",
                "section_id": "ts_3",
            },
            {
                "id": "mc_2",
                "category": "must_cover",
                "question": "Derivation missing",
                "severity": "critical",
                "section_id": "ts_3",
            },
        ]
    )
    presentation = build_qc_warning_presentation(qc, CONCEPT_PLAN)
    assert presentation is not None
    assert presentation["kind"] == "mixed"
    assert presentation["alert_title"] == "Quality review recommended"
    assert len(presentation["formatting_items"]) == 1


def test_llm_only_presentation() -> None:
    qc = _qc_with_failed_checks(
        [
            {
                "id": "mc_2",
                "category": "must_cover",
                "question": "Missing derivation",
                "severity": "critical",
                "section_id": "ts_3",
            }
        ]
    )
    presentation = build_qc_warning_presentation(qc, CONCEPT_PLAN)
    assert presentation is not None
    assert presentation["kind"] == "llm_content"
    assert presentation["alert_title"] == "Quality review recommended"
    assert presentation["formatting_items"] == []


def test_structure_coverage_maps_section_headings() -> None:
    qc = _qc_with_failed_checks(
        [
            {
                "id": "det_structure_coverage",
                "category": "structure",
                "question": "Sections exist?",
                "severity": "critical",
                "evidence": "Missing section ids: ts_1, ts_3",
            }
        ]
    )
    presentation = build_qc_warning_presentation(qc, CONCEPT_PLAN)
    assert presentation is not None
    assert presentation["kind"] == "det_only"
    assert presentation["alert_title"] == "Document structure incomplete"
    message = presentation["structure_items"][0]["user_message"]
    assert "Introduction to Limits" in message
    assert "Derivation of the Power Rule" in message


def test_enrich_qc_result_attaches_humanized_issues() -> None:
    qc = _qc_with_failed_checks(
        [],
        issues=["The revised section ts_3 does not provide a derivation."],
    )
    enriched = enrich_qc_result_for_client(qc, CONCEPT_PLAN)
    assert enriched is not None
    assert enriched["humanized_issues"] == [
        'The "Derivation of the Power Rule" section does not provide a derivation.'
    ]
