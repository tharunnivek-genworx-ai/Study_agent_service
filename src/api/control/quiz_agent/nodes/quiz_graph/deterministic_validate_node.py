"""Deterministic structural validation before LLM quality check.

Graph node (pre-QC gate)
------------------------
Runs ``run_deterministic_quiz_checks`` on ``parsed_questions``. On pass, sets
``validated_questions`` and ``struct_validation_passed=True`` for QC.

On fail, increments ``gen_attempt`` and sets ``gen_feedback`` for the generator
retry loop (max ``MAX_GEN_ATTEMPTS``). Permanent failure builds a synthetic
``qc_result`` and routes to ``persist_quiz_draft``.

Overflow (more questions than requested) routes to ``question_prune`` instead of
re-running patch/insert. After a successful prune, ``present_without_qc`` skips
QC and persists the draft for the mentor.

Routing: struct pass → ``quality_check`` (or ``persist_quiz_draft`` when
``present_without_qc``); overflow → ``quiz_generator`` with prune mode;
retry → ``quiz_generator``; permanent fail → ``persist_quiz_draft``.
"""

from __future__ import annotations

from typing import Any

from src.api.control.quiz_agent.states.quiz_graph.quiz_state import QuizGraphState
from src.api.utils.quiz_utils.graph.constants import (
    MAX_GEN_ATTEMPTS,
    QUESTION_PRUNE_MODE,
)
from src.api.utils.quiz_utils.graph.node_helpers import (
    format_gen_feedback_from_checks,
    log_quiz_artifact,
)
from src.api.utils.quiz_utils.quality_check_utils.checks.deterministic import (
    run_deterministic_quiz_checks,
)
from src.api.utils.quiz_utils.quality_check_utils.document.question_merge import (
    prune_questions_to_count,
)
from src.api.utils.quiz_utils.quality_check_utils.results.quiz_result_builder import (
    build_final_quiz_qc_result,
)


def _overflow_prune_feedback(*, actual: int, expected: int) -> str:
    excess = actual - expected
    return (
        "QUESTION COUNT OVERFLOW — PRUNE REQUIRED\n"
        f"The quiz has {actual} questions but the mentor requested {expected}. "
        f"Remove exactly {excess} question(s) that are not needed and not aligned "
        "with the study material. Prefer removing questions that cannot be answered "
        "from the study material or that duplicate stronger coverage. "
        "Do not insert or rewrite — only remove."
    )


async def deterministic_validate_node(state: QuizGraphState) -> dict[str, Any]:
    """Validate parsed questions structurally; gate entry to QC or generator retry."""
    parsed = state.get("parsed_questions") or []
    gen_attempt = state.get("gen_attempt") or 0
    expected_count = state["question_count"]
    det_checks = run_deterministic_quiz_checks(
        parsed,
        expected_count=expected_count,
    )
    failed = [check for check in det_checks if not check.get("passed", True)]

    if not failed:
        det_return: dict[str, Any] = {
            "validated_questions": parsed,
            "gen_feedback": "",
            "struct_validation_passed": True,
        }
        if state.get("present_without_qc"):
            det_return["qc_passed"] = True
            det_return["qc_failed_permanently"] = False
            det_return["qc_retry_mode"] = "none"
        log_quiz_artifact(
            state,
            "quiz_deterministic",
            {
                "det_checks": det_checks,
                "struct_validation_passed": True,
                "gen_attempt": gen_attempt,
                "parsed_questions": parsed,
                "present_without_qc": bool(state.get("present_without_qc")),
            },
        )
        return det_return

    actual = len(parsed)
    overflow = actual > expected_count
    prefer_remove_ids = list(state.get("qc_reverify_question_ids") or [])

    # Overflow recovery: prune extras (never re-run patch/insert forever).
    if overflow:
        prune_attempt = int(state.get("prune_attempt") or 0)
        if prune_attempt >= 1 or state.get("present_without_qc"):
            # LLM prune did not fix count — deterministic fallback, present without QC.
            pruned = prune_questions_to_count(
                parsed,
                expected_count,
                prefer_remove_ids=prefer_remove_ids,
            )
            det_return = {
                "parsed_questions": pruned,
                "validated_questions": pruned,
                "gen_feedback": "",
                "struct_validation_passed": True,
                "qc_retry_mode": "none",
                "present_without_qc": True,
                "qc_passed": True,
                "qc_failed_permanently": False,
            }
            log_quiz_artifact(
                state,
                "quiz_deterministic",
                {
                    "det_checks": det_checks,
                    "struct_validation_passed": True,
                    "gen_attempt": gen_attempt,
                    "parsed_questions": pruned,
                    "overflow_fallback_prune": True,
                },
            )
            return det_return

        prune_feedback = _overflow_prune_feedback(
            actual=actual,
            expected=expected_count,
        )
        det_return = {
            "gen_attempt": gen_attempt,
            "gen_feedback": prune_feedback,
            "struct_validation_passed": False,
            "qc_retry_mode": QUESTION_PRUNE_MODE,
            "validated_questions": [],
            "present_without_qc": False,
        }
        log_quiz_artifact(
            state,
            "quiz_deterministic",
            {
                "det_checks": det_checks,
                "struct_validation_passed": False,
                "gen_feedback": prune_feedback,
                "gen_attempt": gen_attempt,
                "parsed_questions": parsed,
                "qc_retry_mode": QUESTION_PRUNE_MODE,
            },
        )
        return det_return

    feedback = format_gen_feedback_from_checks(failed)
    new_attempt = gen_attempt + 1
    permanently_failed = new_attempt >= MAX_GEN_ATTEMPTS

    if permanently_failed:
        # Exhausted MAX_GEN_ATTEMPTS — synthesize QC result and persist as failed draft.
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
    # Stop surgical insert/patch loops from re-inserting on non-overflow struct fails.
    if (state.get("qc_retry_mode") or "") in {
        "question_insert",
        "question_patch_then_insert",
    }:
        det_return["qc_retry_mode"] = "question_patch"
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
