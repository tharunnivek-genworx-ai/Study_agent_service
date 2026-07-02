"""Deterministic validation for single-question mentor rework patches."""

from __future__ import annotations

from typing import Any, cast

from src.api.control.quiz_agent.states.quiz_graph.quiz_state import QuizGraphState
from src.api.utils.quiz_utils.graph.node_helpers import (
    format_gen_feedback_from_checks,
    log_quiz_artifact,
)
from src.api.utils.quiz_utils.quality_check_utils.checks.deterministic import (
    run_deterministic_quiz_checks,
)


async def deterministic_validate_question_patches(
    state: QuizGraphState,
) -> dict[str, Any]:
    parsed = state.get("parsed_patches") or []
    expected_count = len(state.get("question_ids") or [])
    det_checks = run_deterministic_quiz_checks(
        parsed,
        expected_count=expected_count,
    )
    failed = [check for check in det_checks if not check.get("passed", True)]

    log_quiz_artifact(
        cast(Any, state),
        "quiz_single_regen_deterministic",
        {
            "det_checks": det_checks,
            "parsed_patches": parsed,
        },
    )

    if not failed:
        return {
            "validated_patches": parsed,
            "struct_validation_passed": True,
        }

    feedback = format_gen_feedback_from_checks(failed)
    return {
        "validated_patches": [],
        "struct_validation_passed": False,
        "error": feedback,
    }
