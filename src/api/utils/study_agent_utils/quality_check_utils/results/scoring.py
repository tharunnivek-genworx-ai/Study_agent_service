# src/api/utils/study_agent_utils/qc/scoring.py
"""Pure-Python QC status derivation — no LLM involved."""

from __future__ import annotations

from typing import Any


def derive_overall_status(
    checks: list[dict[str, Any]],
    hallucination_risk: str,
    is_refusal: bool,
) -> str:
    """Derive the overall QC status from binary check results."""
    if is_refusal:
        return "pass"
    if hallucination_risk == "high":
        return "fail"
    if any(
        not c.get("passed", True) and c.get("severity") == "critical" for c in checks
    ):
        return "fail"
    if hallucination_risk == "medium":
        return "warn"
    if any(not c.get("passed", True) and c.get("severity") == "major" for c in checks):
        return "warn"
    if any(not c.get("passed", True) for c in checks):
        return "warn"
    return "pass"


_CATEGORY_TO_SCORE_KEY: dict[str, str] = {
    "structure": "structure",
    "content_accuracy": "content_accuracy",
    "code_quality": "code_quality",
    "stack_fidelity": "code_quality",
    "teaching_alignment": "teaching_alignment",
    "pitfalls_depth": "section_depth",
    "concept_coverage": "section_depth",
    "must_cover": "section_depth",
    "document_coherence": "section_depth",
}


def _score_from_checks(checks_for_key: list[dict[str, Any]]) -> int | None:
    if not checks_for_key:
        return None
    passed = sum(1 for c in checks_for_key if c.get("passed", False))
    total = len(checks_for_key)
    raw = round(passed / total * 10)
    return max(1, min(10, raw))


def derive_scores(checks: list[dict[str, Any]]) -> dict[str, int | None]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for check in checks:
        category = check.get("category", "")
        score_key = _CATEGORY_TO_SCORE_KEY.get(category)
        if score_key:
            grouped.setdefault(score_key, []).append(check)

    score_keys = [
        "structure",
        "content_accuracy",
        "code_quality",
        "section_depth",
        "teaching_alignment",
    ]
    return {key: _score_from_checks(grouped.get(key, [])) for key in score_keys}


_INTERNAL_SCORE_KEYS = frozenset({"structure", "readability"})


def public_scores(scores: dict[str, int | None]) -> dict[str, int | None]:
    """Return API/DB-facing scores without internal-only routing dimensions."""
    return {
        key: value for key, value in scores.items() if key not in _INTERNAL_SCORE_KEYS
    }


def extract_failed_checks(checks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [c for c in checks if not c.get("passed", True)]


def has_failed_must_cover(failed_checks: list[dict[str, Any]]) -> bool:
    """True when any must_cover checklist item failed QC."""
    return any(
        str(check.get("category", "")) == "must_cover" and not check.get("passed", True)
        for check in failed_checks
    )


def missing_checklist_ids_from_recommendation(
    retry_recommendation: dict[str, Any] | None,
) -> list[str]:
    if not isinstance(retry_recommendation, dict):
        return []
    return [
        str(item_id).strip()
        for item_id in (retry_recommendation.get("missing_checklist_ids") or [])
        if str(item_id).strip()
    ]


def requires_must_cover_retry(
    *,
    failed_checks: list[dict[str, Any]],
    retry_recommendation: dict[str, Any] | None,
) -> bool:
    """True when checklist gaps remain and the pipeline should retry generation."""
    if has_failed_must_cover(failed_checks):
        return True
    return bool(missing_checklist_ids_from_recommendation(retry_recommendation))


def is_qc_deliverable(
    *,
    overall_status: str,
    failed_checks: list[dict[str, Any]],
    hallucination_risk: str,
    is_refusal: bool,
    retry_recommendation: dict[str, Any] | None = None,
) -> bool:
    """Return True when QC result is deliverable despite overall_status nuances.

    ``warn`` is deliverable when no critical failures remain, hallucination risk
    is not high, and no must_cover checklist item failed or is missing.
    ``overall_status`` is unchanged for reporting.
    """
    if is_refusal:
        return True
    if requires_must_cover_retry(
        failed_checks=failed_checks,
        retry_recommendation=retry_recommendation,
    ):
        return False
    if overall_status == "pass":
        return True
    if overall_status == "fail":
        return False
    if overall_status == "warn":
        if hallucination_risk == "high":
            return False
        if any(c.get("severity") == "critical" for c in failed_checks):
            return False
        return True
    return False
