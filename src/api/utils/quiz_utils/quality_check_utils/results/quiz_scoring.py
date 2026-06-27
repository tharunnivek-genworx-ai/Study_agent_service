"""Pure-Python quiz QC status derivation — no LLM involved."""

from __future__ import annotations

from typing import Any


def derive_quiz_overall_status(
    checks: list[dict[str, Any]],
    wrong_answer_risk: str,
) -> str:
    """Derive overall QC status from binary check results and wrong_answer_risk."""
    if wrong_answer_risk == "high":
        return "fail"
    if any(
        not c.get("passed", True) and c.get("severity") == "critical" for c in checks
    ):
        return "fail"
    if wrong_answer_risk == "medium":
        return "warn"
    if any(not c.get("passed", True) and c.get("severity") == "major" for c in checks):
        return "warn"
    if any(not c.get("passed", True) for c in checks):
        return "warn"
    return "pass"


_CATEGORY_TO_SCORE_KEY: dict[str, str] = {
    "answer_correctness": "answer_correctness",
    "question_quality": "question_quality",
    "topic_relevance": "question_quality",
    "option_quality": "question_quality",
    "question_clarity": "question_quality",
    "explanation_quality": "question_quality",
    "difficulty_alignment": "difficulty_alignment",
    "duplicate_overlap": "duplicate_overlap",
    "quiz_coherence": "quiz_coherence",
}

_LEGACY_QUALITY_SCORE_KEYS = (
    "topic_relevance",
    "option_quality",
    "question_clarity",
    "explanation_quality",
)


def _score_from_checks(checks_for_key: list[dict[str, Any]]) -> int | None:
    if not checks_for_key:
        return None
    passed = sum(1 for c in checks_for_key if c.get("passed", False))
    total = len(checks_for_key)
    raw = round(passed / total * 10)
    return max(1, min(10, raw))


def derive_quiz_scores(checks: list[dict[str, Any]]) -> dict[str, int | None]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for check in checks:
        category = str(check.get("category", ""))
        score_key = _CATEGORY_TO_SCORE_KEY.get(category)
        if score_key:
            grouped.setdefault(score_key, []).append(check)

    scores = {
        key: _score_from_checks(grouped.get(key, []))
        for key in dict.fromkeys(_CATEGORY_TO_SCORE_KEY.values())
    }
    quality_score = scores.get("question_quality")
    if quality_score is not None:
        for legacy_key in _LEGACY_QUALITY_SCORE_KEYS:
            scores[legacy_key] = quality_score
    return scores


def extract_failed_checks(checks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [c for c in checks if not c.get("passed", True)]


def has_failed_answer_correctness(failed_checks: list[dict[str, Any]]) -> bool:
    return any(
        str(check.get("category", "")) == "answer_correctness"
        and not check.get("passed", True)
        for check in failed_checks
    )


def missing_concepts_from_recommendation(
    retry_recommendation: dict[str, Any] | None,
) -> list[str]:
    if not isinstance(retry_recommendation, dict):
        return []
    return [
        str(concept).strip()
        for concept in (retry_recommendation.get("missing_concepts") or [])
        if str(concept).strip()
    ]


def is_quiz_qc_deliverable(
    *,
    overall_status: str,
    failed_checks: list[dict[str, Any]],
    wrong_answer_risk: str,
    retry_recommendation: dict[str, Any] | None = None,
) -> bool:
    """Return True when quiz QC result is deliverable despite warn status."""
    if has_failed_answer_correctness(failed_checks):
        return False
    if overall_status == "pass":
        return True
    if missing_concepts_from_recommendation(retry_recommendation):
        mode = str((retry_recommendation or {}).get("mode") or "none")
        if failed_checks or mode != "none":
            return False
    if overall_status == "fail":
        return False
    if overall_status == "warn":
        if wrong_answer_risk == "high":
            return False
        if any(c.get("severity") == "critical" for c in failed_checks):
            return False
        return True
    return False
