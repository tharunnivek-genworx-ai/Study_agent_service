"""Merge targeted quiz QC verification checks into a prior full QC result."""

from __future__ import annotations

from typing import Any

from src.api.control.quiz_agent.prompts import (
    LLM_QUIZ_WIDE_CATEGORIES,
    PER_QUESTION_CATEGORIES,
)


def _reverify_question_ids(reverify_question_ids: list[str]) -> set[str]:
    return {
        str(question_id).strip()
        for question_id in reverify_question_ids
        if str(question_id).strip()
    }


def check_targets_reverify(
    check: dict[str, Any],
    *,
    reverify_question_ids: set[str],
) -> bool:
    """Return True when a prior check should be replaced by targeted re-verification."""
    category = str(check.get("category", ""))
    question_id = str(check.get("question_id", "") or "").strip()

    if category in PER_QUESTION_CATEGORIES:
        return bool(question_id and question_id in reverify_question_ids)

    if category in LLM_QUIZ_WIDE_CATEGORIES:
        return True

    return False


def _dedup_key(check: dict[str, Any]) -> tuple[str, ...]:
    category = str(check.get("category", ""))
    if category in PER_QUESTION_CATEGORIES:
        return (category, str(check.get("question_id", "") or ""))
    return (category, str(check.get("id", "") or ""))


def _dedup_checks(checks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: dict[tuple[str, ...], int] = {}
    for index, check in enumerate(checks):
        seen[_dedup_key(check)] = index
    surviving = set(seen.values())
    return [check for index, check in enumerate(checks) if index in surviving]


def merge_targeted_qc_checks(
    prior_qc_result: dict[str, Any],
    new_verification: dict[str, Any] | None,
    *,
    reverify_question_ids: list[str],
) -> list[dict[str, Any]]:
    """Keep prior checks outside re-verify scope; replace scoped checks with new results."""
    question_ids = _reverify_question_ids(reverify_question_ids)

    prior_checks = [
        check
        for check in (prior_qc_result.get("checks") or [])
        if isinstance(check, dict)
    ]
    kept = [
        check
        for check in prior_checks
        if not check_targets_reverify(check, reverify_question_ids=question_ids)
    ]

    new_checks = [
        check
        for check in ((new_verification or {}).get("checks") or [])
        if isinstance(check, dict)
    ]

    return _dedup_checks(kept + new_checks)
