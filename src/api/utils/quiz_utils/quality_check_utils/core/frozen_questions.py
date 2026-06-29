"""Frozen question IDs for incremental quiz QC on retries."""

from __future__ import annotations

from typing import Any

from src.api.control.quiz_agent.prompts.quiz_qc_check_definitions import (
    PER_QUESTION_CATEGORIES,
)


def accumulate_frozen_question_ids(
    checks: list[dict[str, Any]],
    existing_question_ids: list[str] | None,
) -> list[str]:
    """Merge fully passing per-question checks into the frozen question set."""
    frozen_ids = set(existing_question_ids or [])
    passes_by_question: dict[str, list[bool]] = {}

    for check in checks:
        if not isinstance(check, dict):
            continue
        category = str(check.get("category", ""))
        if category not in PER_QUESTION_CATEGORIES:
            continue
        question_id = str(check.get("question_id", "")).strip()
        if not question_id:
            continue
        passes_by_question.setdefault(question_id, []).append(
            bool(check.get("passed", False))
        )

    for question_id, passes in passes_by_question.items():
        if passes and all(passes):
            frozen_ids.add(question_id)

    return sorted(frozen_ids)
