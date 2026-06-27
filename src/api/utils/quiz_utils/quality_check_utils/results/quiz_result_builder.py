"""Merge deterministic + LLM verification checks into a final quiz QC result."""

from __future__ import annotations

from typing import Any

from src.api.utils.quiz_utils.quality_check_utils.results.quiz_scoring import (
    derive_quiz_overall_status,
    derive_quiz_scores,
    extract_failed_checks,
)


def build_final_quiz_qc_result(
    verification: dict[str, Any] | None,
    det_checks: list[dict[str, Any]],
    *,
    questions: list[dict[str, Any]] | None = None,
    model: str | None = None,
) -> dict[str, Any]:
    """Merge deterministic + LLM checks and derive status/scores."""
    ver = verification or {}
    llm_checks = [
        check for check in (ver.get("checks") or []) if isinstance(check, dict)
    ]

    # Deterministic checks take precedence for duplicate ids/categories they own.
    det_ids = {str(c.get("id", "")) for c in det_checks}
    merged_llm = [
        check for check in llm_checks if str(check.get("id", "")) not in det_ids
    ]
    all_checks = det_checks + merged_llm

    wrong_answer_risk = str(ver.get("wrong_answer_risk", "none"))
    issues = list(ver.get("issues", []) or [])
    overall_status = derive_quiz_overall_status(all_checks, wrong_answer_risk)
    scores = derive_quiz_scores(all_checks)
    failed = extract_failed_checks(all_checks)

    corrective = str(ver.get("corrective_instructions", "")).strip()
    summary = str(ver.get("summary", "")).strip()

    result: dict[str, Any] = {
        "overall_status": overall_status,
        "wrong_answer_risk": wrong_answer_risk,
        "scores": scores,
        "checks": all_checks,
        "failed_checks": failed,
        "issues": issues,
        "corrective_instructions": corrective,
        "summary": summary,
        "qc_llm_model_used": model,
    }

    recommendation = ver.get("retry_recommendation")
    if isinstance(recommendation, dict):
        result["retry_recommendation"] = recommendation

    if questions is not None:
        result["question_count"] = len(questions)

    return result
