"""Classify quiz QC failures into question-level retry routing modes."""

from __future__ import annotations

import ast
import re
from typing import Any, cast

from src.api.control.quiz_agent.prompts import (
    PER_QUESTION_CATEGORIES,
    QUIZ_WIDE_CATEGORIES,
)
from src.api.schemas.qc_schemas import (
    QuizRetryMode,
    QuizRetryRoutingResult,
)

_COVERAGE_EVIDENCE_RE = re.compile(r"coverage\s*=\s*(\[[^\]]*\])", re.IGNORECASE)

_VALID_MODES: frozenset[str] = frozenset(
    {
        "question_patch",
        "question_insert",
        "question_patch_then_insert",
        "question_prune",
        "full_regeneration",
        "none",
    }
)

_FULL_REGEN_FAILED_QUESTION_THRESHOLD = 4


def _failed_checks(qc_result: dict[str, Any]) -> list[dict[str, Any]]:
    explicit = qc_result.get("failed_checks")
    if isinstance(explicit, list) and explicit:
        return [check for check in explicit if isinstance(check, dict)]

    checks = qc_result.get("checks")
    if not isinstance(checks, list):
        return []
    return [
        check
        for check in checks
        if isinstance(check, dict) and not check.get("passed", True)
    ]


def _failure_record(check: dict[str, Any]) -> dict[str, str]:
    return {
        "category": str(check.get("category", "")),
        "evidence": str(check.get("evidence", "")),
        "corrective_hint": str(check.get("corrective_hint", "")),
    }


def _map_failures_to_questions(
    failed: list[dict[str, Any]],
) -> tuple[set[str], set[str], dict[str, list[dict[str, str]]], int]:
    failed_question_ids: set[str] = set()
    missing_concepts: set[str] = set()
    failures_by_question: dict[str, list[dict[str, str]]] = {}
    unmapped_count = 0

    for check in failed:
        category = str(check.get("category", ""))

        if category in PER_QUESTION_CATEGORIES:
            question_id = str(check.get("question_id", "")).strip()
            if question_id:
                failed_question_ids.add(question_id)
                failures_by_question.setdefault(question_id, []).append(
                    _failure_record(check)
                )
            else:
                unmapped_count += 1
            continue

        # Coverage gaps are extracted from quiz_summary / structured evidence
        # in ``_missing_concepts_from_qc`` — never treat raw evidence as a concept.
        if category == "duplicate_overlap":
            continue

        if category in QUIZ_WIDE_CATEGORIES:
            continue

        unmapped_count += 1

    return failed_question_ids, missing_concepts, failures_by_question, unmapped_count


def _parse_coverage_from_evidence(evidence: str) -> set[str]:
    """Parse ``coverage=['A', 'B']`` blobs from duplicate_overlap evidence."""
    match = _COVERAGE_EVIDENCE_RE.search(str(evidence or ""))
    if not match:
        return set()
    try:
        items = ast.literal_eval(match.group(1))
    except (ValueError, SyntaxError):
        return set()
    if not isinstance(items, list):
        return set()
    return {str(item).strip() for item in items if str(item).strip()}


def _missing_concepts_from_qc(
    qc_result: dict[str, Any],
    failed: list[dict[str, Any]],
) -> set[str]:
    """Collect real coverage-gap concepts (never raw evidence strings)."""
    concepts: set[str] = set()
    summary = qc_result.get("quiz_summary")
    if isinstance(summary, dict):
        for item in summary.get("coverage_issues") or []:
            text = str(item).strip()
            if text:
                concepts.add(text)

    for check in failed:
        if str(check.get("category", "")) != "duplicate_overlap":
            continue
        if check.get("passed", True):
            continue
        concepts |= _parse_coverage_from_evidence(str(check.get("evidence", "")))

    return concepts


def _missing_concepts_from_recommendation(qc_result: dict[str, Any]) -> set[str]:
    recommendation = qc_result.get("retry_recommendation")
    if not isinstance(recommendation, dict):
        return set()
    return {
        str(concept).strip()
        for concept in (recommendation.get("missing_concepts") or [])
        if str(concept).strip()
        # Guard against contaminated evidence blobs leaking into recommendations.
        and not str(concept).strip().lower().startswith("duplicates=")
    }


def _should_force_full_regeneration(
    *,
    failed: list[dict[str, Any]],
    failed_question_ids: set[str],
    wrong_answer_risk: str,
    unmapped_count: int,
    total_questions: int,
) -> tuple[bool, str]:
    if len(failed_question_ids) >= _FULL_REGEN_FAILED_QUESTION_THRESHOLD:
        return (
            True,
            f"{len(failed_question_ids)} distinct failed question ids",
        )

    if wrong_answer_risk == "high":
        failed_categories = {
            str(check.get("category", ""))
            for check in failed
            if not check.get("passed", True)
        }
        non_risk_categories = failed_categories - {"answer_correctness"}
        if len(non_risk_categories) >= 1:
            return True, "wrong_answer_risk high with multiple category failures"

    answer_correctness_failures = sum(
        1
        for check in failed
        if str(check.get("category", "")) == "answer_correctness"
        and not check.get("passed", True)
    )
    quiz_size = max(1, total_questions)
    if answer_correctness_failures > quiz_size / 3:
        return (
            True,
            "answer_correctness fails on more than a third of questions",
        )

    if unmapped_count >= 3:
        return True, f"{unmapped_count} unmapped failed checks"

    return False, ""


def _deterministic_mode(
    *,
    failed_question_ids: set[str],
    missing_concepts: set[str],
) -> QuizRetryMode:
    has_failed = bool(failed_question_ids)
    has_missing = bool(missing_concepts)
    if not has_failed and not has_missing:
        return "none"
    if has_failed and has_missing:
        return "question_patch_then_insert"
    if has_missing:
        return "question_insert"
    return "question_patch"


def _coerce_llm_recommendation_mode(raw_mode: Any) -> QuizRetryMode | None:
    mode = str(raw_mode or "").strip()
    if mode in _VALID_MODES:
        return cast(QuizRetryMode, mode)
    return None


def _reconcile_mode(
    *,
    deterministic: QuizRetryMode,
    llm_recommendation_mode: QuizRetryMode | None,
    force_full_regen: bool,
    failed_question_ids: set[str],
    missing_concepts: set[str],
) -> QuizRetryMode:
    if force_full_regen:
        return "full_regeneration"
    if deterministic == "none":
        return "none"

    if llm_recommendation_mode is None:
        return deterministic

    if llm_recommendation_mode == "none":
        return deterministic

    has_failed = bool(failed_question_ids)
    has_missing = bool(missing_concepts)

    if llm_recommendation_mode == "question_patch" and has_failed and not has_missing:
        return "question_patch"
    if llm_recommendation_mode == "question_insert" and has_missing and not has_failed:
        return "question_insert"
    if (
        llm_recommendation_mode == "question_patch_then_insert"
        and has_failed
        and has_missing
    ):
        return "question_patch_then_insert"

    return deterministic


def _build_question_failures(
    failed_question_ids: list[str],
    failures_by_question: dict[str, list[dict[str, str]]],
    questions_by_id: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    bundles: list[dict[str, Any]] = []
    for question_id in failed_question_ids:
        question = questions_by_id.get(question_id, {})
        bundles.append(
            {
                "question_id": question_id,
                "order_index": question.get("order_index"),
                "failures": failures_by_question.get(question_id, []),
            }
        )
    return bundles


def classify_quiz_retry_routing(
    qc_result: dict[str, Any],
    questions: list[dict[str, Any]],
) -> QuizRetryRoutingResult:
    """Map QC failures to a retry mode and per-question rework targets."""
    failed = _failed_checks(qc_result)
    if not failed:
        return QuizRetryRoutingResult(
            mode="none",
            failed_question_ids=[],
            missing_concepts=[],
            question_failures=[],
            rationale="no failed checks",
        )

    failed_question_ids, _unused_missing, failures_by_question, unmapped_count = (
        _map_failures_to_questions(failed)
    )
    del _unused_missing
    missing_concepts = _missing_concepts_from_qc(qc_result, failed)
    missing_concepts |= _missing_concepts_from_recommendation(qc_result)

    wrong_answer_risk = str(qc_result.get("wrong_answer_risk", "none"))
    force_full_regen, force_reason = _should_force_full_regeneration(
        failed=failed,
        failed_question_ids=failed_question_ids,
        wrong_answer_risk=wrong_answer_risk,
        unmapped_count=unmapped_count,
        total_questions=len(questions),
    )

    deterministic = _deterministic_mode(
        failed_question_ids=failed_question_ids,
        missing_concepts=missing_concepts,
    )

    recommendation = qc_result.get("retry_recommendation")
    llm_recommendation_mode: QuizRetryMode | None = None
    llm_recommendation_rationale = ""
    if isinstance(recommendation, dict):
        llm_recommendation_mode = _coerce_llm_recommendation_mode(
            recommendation.get("mode")
        )
        llm_recommendation_rationale = str(recommendation.get("rationale", "")).strip()

    mode = _reconcile_mode(
        deterministic=deterministic,
        llm_recommendation_mode=llm_recommendation_mode,
        force_full_regen=force_full_regen,
        failed_question_ids=failed_question_ids,
        missing_concepts=missing_concepts,
    )

    if force_full_regen:
        rationale = force_reason
    elif llm_recommendation_rationale and llm_recommendation_mode == mode:
        rationale = llm_recommendation_rationale
    elif mode == deterministic:
        rationale = f"deterministic routing: {mode}"
    else:
        rationale = f"deterministic {deterministic} reconciled to {mode}"

    sorted_failed_ids = sorted(failed_question_ids)
    sorted_missing = sorted(missing_concepts)
    questions_by_id = {
        str(q.get("question_id", "")).strip(): q
        for q in questions
        if str(q.get("question_id", "")).strip()
    }

    return QuizRetryRoutingResult(
        mode=mode,
        failed_question_ids=sorted_failed_ids,
        missing_concepts=sorted_missing,
        question_failures=_build_question_failures(
            sorted_failed_ids,
            failures_by_question,
            questions_by_id,
        ),
        rationale=rationale,
    )
