"""Deterministic structural validation before LLM quality check."""

from __future__ import annotations

from typing import Any

from src.api.control.quiz_agent.states.quiz_state import QuizGraphState
from src.api.utils.quiz_utils.graph.constants import MAX_GEN_ATTEMPTS
from src.api.utils.quiz_utils.graph.node_helpers import (
    format_gen_feedback_from_checks,
    log_quiz_artifact,
)
from src.api.utils.quiz_utils.quality_check_utils.checks.deterministic import (
    run_deterministic_quiz_checks,
)
from src.api.utils.quiz_utils.quality_check_utils.results.quiz_result_builder import (
    build_final_quiz_qc_result,
)


async def deterministic_validate_node(state: QuizGraphState) -> dict[str, Any]:
    parsed = state.get("parsed_questions") or []
    gen_attempt = state.get("gen_attempt") or 0
    det_checks = run_deterministic_quiz_checks(
        parsed,
        expected_count=state["question_count"],
    )
    failed = [check for check in det_checks if not check.get("passed", True)]

    if not failed:
        det_return = {
            "validated_questions": parsed,
            "gen_feedback": "",
            "struct_validation_passed": True,
        }
        log_quiz_artifact(
            state,
            "quiz_deterministic",
            {
                "det_checks": det_checks,
                "struct_validation_passed": True,
                "gen_attempt": gen_attempt,
                "parsed_questions": parsed,
            },
        )
        return det_return

    feedback = format_gen_feedback_from_checks(failed)
    new_attempt = gen_attempt + 1
    permanently_failed = new_attempt >= MAX_GEN_ATTEMPTS

    if permanently_failed:
        qc_result = build_final_quiz_qc_result(
            None,
            det_checks,
            questions=parsed,
        )
        det_return = {
            "validated_questions": parsed,
            "gen_attempt": new_attempt,
            "gen_feedback": feedback,
            "struct_validation_passed": False,
            "qc_failed_permanently": True,
            "qc_result": qc_result,
        }
        log_quiz_artifact(
            state,
            "quiz_deterministic",
            {
                "det_checks": det_checks,
                "struct_validation_passed": False,
                "gen_feedback": feedback,
                "gen_attempt": new_attempt,
                "parsed_questions": parsed,
            },
        )
        return det_return

    det_return = {
        "gen_attempt": new_attempt,
        "gen_feedback": feedback,
        "struct_validation_passed": False,
        "validated_questions": [],
    }
    log_quiz_artifact(
        state,
        "quiz_deterministic",
        {
            "det_checks": det_checks,
            "struct_validation_passed": False,
            "gen_feedback": feedback,
            "gen_attempt": new_attempt,
            "parsed_questions": parsed,
        },
    )
    return det_return
