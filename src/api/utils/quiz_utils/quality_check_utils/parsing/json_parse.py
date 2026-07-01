"""Robust JSON parsing for quiz QC LLM responses."""

from __future__ import annotations

import logging
from typing import Any

from src.api.control.quiz_agent.prompts import (
    PER_QUESTION_CATEGORIES,
)
from src.api.utils.study_agent_utils.quality_check_utils.parsing.json_parse import (
    parse_llm_json_object,
)

logger = logging.getLogger(__name__)

_PER_QUESTION_DIMENSION_COUNT = len(PER_QUESTION_CATEGORIES)

_QUESTION_RESULT_REQUIRED_FIELDS = (
    "question_id",
    "question_number",
    "answer_correctness_passed",
    "answer_evidence",
    "quality_passed",
    "quality_evidence",
    "corrective_hint",
)


def expected_quiz_qc_question_result_count(question_count: int) -> int:
    """Expected question_results entries in the LLM response (one per question)."""
    return question_count


def expected_quiz_qc_check_count(question_count: int) -> int:
    """Expected per-question checks after normalization (2 × N)."""
    return question_count * _PER_QUESTION_DIMENSION_COUNT


def _is_valid_question_result(result: Any) -> bool:
    if not isinstance(result, dict):
        return False
    for field in _QUESTION_RESULT_REQUIRED_FIELDS:
        if field not in result:
            return False
    if not isinstance(result["answer_correctness_passed"], bool):
        return False
    if not isinstance(result["quality_passed"], bool):
        return False
    return True


def _question_results_complete_for_question_count(
    question_results: list[Any],
    question_count: int,
) -> bool:
    if not isinstance(question_results, list):
        return False
    if len(question_results) != question_count:
        return False
    return all(_is_valid_question_result(result) for result in question_results)


def expand_question_results_to_checks(
    question_results: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Convert compact per-question question_result objects into scoring checks."""
    checks: list[dict[str, Any]] = []
    for result in question_results:
        question_id = str(result.get("question_id", "")).strip()
        question_number = result.get("question_number")
        corrective_hint = str(result.get("corrective_hint", "")).strip()

        answer_passed = bool(result.get("answer_correctness_passed", False))
        checks.append(
            {
                "id": f"answer_correctness_{question_number or question_id}",
                "category": "answer_correctness",
                "question": f"Q{question_number}: Is the marked answer correct?",
                "passed": answer_passed,
                "severity": "critical",
                "evidence": str(result.get("answer_evidence", "")),
                "corrective_hint": corrective_hint if not answer_passed else "",
                "question_number": question_number,
                "question_id": question_id,
            }
        )

        quality_passed = bool(result.get("quality_passed", False))
        checks.append(
            {
                "id": f"question_quality_{question_number or question_id}",
                "category": "question_quality",
                "question": f"Q{question_number}: Is question quality acceptable?",
                "passed": quality_passed,
                "severity": "major",
                "evidence": str(result.get("quality_evidence", "")),
                "corrective_hint": corrective_hint if not quality_passed else "",
                "question_number": question_number,
                "question_id": question_id,
            }
        )
    return checks


def expand_quiz_summary_to_checks(quiz_summary: dict[str, Any]) -> list[dict[str, Any]]:
    """Convert compact quiz_summary rollup into synthetic wide checks for scoring."""
    counts = quiz_summary.get("difficulty_counts") or {}
    difficulty_ok = bool(quiz_summary.get("difficulty_ok"))
    count_evidence = (
        f"easy={counts.get('easy', 0)}, medium={counts.get('medium', 0)}, "
        f"hard={counts.get('hard', 0)}"
    )
    duplicate_concepts = [
        str(item).strip()
        for item in (quiz_summary.get("duplicate_concepts") or [])
        if str(item).strip()
    ]
    coverage_issues = [
        str(item).strip()
        for item in (quiz_summary.get("coverage_issues") or [])
        if str(item).strip()
    ]
    duplicate_ok = not duplicate_concepts and not coverage_issues
    duplicate_evidence = (
        "No duplicate concepts or coverage gaps."
        if duplicate_ok
        else f"duplicates={duplicate_concepts}; coverage={coverage_issues}"
    )

    return [
        {
            "id": "difficulty_alignment",
            "category": "difficulty_alignment",
            "question": "Does difficulty match the requested profile?",
            "passed": difficulty_ok,
            "severity": "major",
            "evidence": count_evidence,
            "corrective_hint": "" if difficulty_ok else "Rebalance easy/medium/hard.",
        },
        {
            "id": "duplicate_overlap",
            "category": "duplicate_overlap",
            "question": "Are concepts covered without redundancy?",
            "passed": duplicate_ok,
            "severity": "major",
            "evidence": duplicate_evidence,
            "corrective_hint": ""
            if duplicate_ok
            else "Remove duplicates or add missing concept coverage.",
        },
    ]


def normalize_quiz_qc_response(obj: dict[str, Any]) -> dict[str, Any]:
    """Expand question_results + quiz_summary into the internal checks array."""
    question_results = [
        result
        for result in (obj.get("question_results") or [])
        if isinstance(result, dict)
    ]
    per_question = expand_question_results_to_checks(question_results)
    summary = obj.get("quiz_summary")
    synthetic_wide = (
        expand_quiz_summary_to_checks(summary) if isinstance(summary, dict) else []
    )
    return {**obj, "checks": per_question + synthetic_wide}


def _is_valid_quiz_summary(summary: Any) -> bool:
    if not isinstance(summary, dict):
        return False
    if "difficulty_ok" not in summary:
        return False
    counts = summary.get("difficulty_counts")
    if not isinstance(counts, dict):
        return False
    for key in ("easy", "medium", "hard"):
        if key not in counts:
            return False
    for field in ("duplicate_concepts", "coverage_issues"):
        value = summary.get(field)
        if not isinstance(value, list):
            return False
    return True


def is_valid_quiz_qc_response(
    obj: dict[str, Any],
    *,
    question_count: int | None = None,
) -> bool:
    """True when parsed JSON matches the quiz QC verification contract."""
    if "question_results" not in obj or "quiz_summary" not in obj:
        return False
    question_results = obj["question_results"]
    if not isinstance(question_results, list) or not question_results:
        return False
    if not _is_valid_quiz_summary(obj.get("quiz_summary")):
        return False
    for field in (
        "wrong_answer_risk",
        "corrective_instructions",
        "retry_recommendation",
    ):
        if field not in obj:
            return False
    if question_count is not None and not _question_results_complete_for_question_count(
        question_results, question_count
    ):
        return False
    return True


def parse_quiz_qc_response(
    raw: str,
    label: str = "Quiz QC",
    *,
    question_count: int | None = None,
) -> dict[str, Any] | None:
    """Parse, validate, and normalize a quiz QC verification response."""
    parsed = parse_llm_json_object(raw, label)
    if parsed is None:
        return None
    if not is_valid_quiz_qc_response(parsed, question_count=question_count):
        logger.warning(
            "%s response JSON is not a valid quiz QC object (keys=%s, question_results=%s, expected=%s)",
            label,
            sorted(parsed.keys()),
            len(parsed.get("question_results") or []),
            expected_quiz_qc_question_result_count(question_count)
            if question_count is not None
            else "?",
        )
        return None
    return normalize_quiz_qc_response(parsed)
