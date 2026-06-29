"""Run deterministic + LLM quality check on the generated quiz."""

from __future__ import annotations

import logging
from typing import Any, cast

from langchain_core.runnables import RunnableConfig

from src.api.config.llm_config import llm_settings
from src.api.control.quiz_agent.prompts import (
    quiz_qc_prompt,
    quiz_qc_retry_verification_prompt,
)
from src.api.control.quiz_agent.states.quiz_state import QuizGraphState
from src.api.schemas.common.generation_diagnostics_schema import QcInfraErrorType
from src.api.schemas.qc_schemas.quiz_retry_routing_schema import QuizRetryRoutingResult
from src.api.utils.quiz_utils.generation.question_parsing import questions_for_qc
from src.api.utils.quiz_utils.graph.constants import MAX_QC_ATTEMPTS
from src.api.utils.quiz_utils.graph.node_helpers import (
    build_qc_pass_decision,
    log_qc_artifacts,
    qc_infra_failure_return,
)
from src.api.utils.quiz_utils.quality_check_utils.checks.deterministic import (
    run_deterministic_quiz_checks,
)
from src.api.utils.quiz_utils.quality_check_utils.core.frozen_questions import (
    accumulate_frozen_question_ids,
)
from src.api.utils.quiz_utils.quality_check_utils.document.targeted_merge import (
    merge_targeted_qc_checks,
)
from src.api.utils.quiz_utils.quality_check_utils.results.feedback import (
    format_qc_feedback,
)
from src.api.utils.quiz_utils.quality_check_utils.results.quiz_result_builder import (
    build_final_quiz_qc_result,
)
from src.api.utils.quiz_utils.quality_check_utils.results.quiz_retry_routing import (
    classify_quiz_retry_routing,
)
from src.api.utils.quiz_utils.quality_check_utils.results.quiz_scoring import (
    is_quiz_qc_deliverable,
)
from src.api.utils.quiz_utils.quality_check_utils.verification.quiz_verification_pass import (
    run_quiz_verification_pass,
)

logger = logging.getLogger(__name__)


async def quality_check_node(
    state: QuizGraphState,
    config: RunnableConfig,
) -> dict[str, Any]:
    """Run deterministic + LLM quality check on the generated quiz."""
    current_attempt = state.get("qc_attempt") or 0

    if state.get("terminal_llm_failure"):
        logger.info("Skipping QC: terminal LLM failure")
        return {
            "qc_passed": True,
            "qc_result": state.get("qc_result"),
            "qc_feedback": "",
            "qc_attempt": current_attempt,
            "qc_failed_permanently": bool(state.get("qc_failed_permanently")),
        }

    if state.get("error") or not state.get("validated_questions"):
        logger.info("Skipping QC: error or no generated questions")
        return {
            "qc_passed": True,
            "qc_result": None,
            "qc_feedback": "",
            "qc_attempt": current_attempt,
            "qc_failed_permanently": False,
        }

    validated = state.get("validated_questions") or []
    det_checks = run_deterministic_quiz_checks(
        validated,
        expected_count=state["question_count"],
    )
    questions_for_qc_payload = questions_for_qc(validated)

    fixed_questions = state.get("fixed_questions")
    is_targeted = bool(fixed_questions)
    verification_mode = "targeted" if is_targeted else "full"

    build_user: Any
    frozen_ids: set[str] = set()
    reverify_for_merge: list[str] = []
    prior_qc_result: dict[str, Any] | None = None
    questions_for_eval = questions_for_qc_payload

    if is_targeted:
        prior_qc_result = state.get("qc_result") or {}
        build_user = quiz_qc_retry_verification_prompt.build_user_message
        user_kwargs = {
            "topic_title": state.get("node_title") or "",
            "difficulty": state.get("difficulty") or "mixed",
            "question_count": state["question_count"],
            "study_material_content": state.get("study_material_content") or "",
            "revised_questions": fixed_questions or [],
            "full_quiz_questions": questions_for_qc_payload,
            "question_failures": state.get("qc_question_failures") or [],
            "domain": state.get("domain"),
        }
        system_prompt = quiz_qc_retry_verification_prompt.SYSTEM_PROMPT
        graph_node = "qc_retry_verification"
        pass_label = "Quiz targeted QC"
    else:
        prior_qc_result = (
            state.get("qc_result") if state.get("qc_frozen_question_ids") else None
        )
        frozen_ids = {
            str(question_id).strip()
            for question_id in (state.get("qc_frozen_question_ids") or [])
            if str(question_id).strip()
        }
        questions_for_eval = questions_for_qc_payload
        if frozen_ids:
            reverify_for_merge = [
                str(q.get("question_id", "")).strip()
                for q in questions_for_qc_payload
                if str(q.get("question_id", "")).strip()
                and str(q.get("question_id", "")).strip() not in frozen_ids
            ]
            questions_for_eval = [
                q
                for q in questions_for_qc_payload
                if str(q.get("question_id", "")).strip() not in frozen_ids
            ]

        build_user = quiz_qc_prompt.build_user_message
        user_kwargs = {
            "topic_title": state.get("node_title") or "",
            "difficulty": state.get("difficulty") or "mixed",
            "question_count": len(questions_for_eval),
            "generation_mode": state.get("mode") or "generate",
            "study_material_content": state.get("study_material_content") or "",
            "quiz_questions": questions_for_eval,
            "domain": state.get("domain"),
            "frozen_question_ids": sorted(frozen_ids) if frozen_ids else None,
        }
        system_prompt = quiz_qc_prompt.build_system_prompt(domain=state.get("domain"))
        graph_node = "quality_check"
        pass_label = "Quiz QC"

    qc_question_count = (
        len(fixed_questions or []) if is_targeted else len(questions_for_eval)
    )

    verification, verification_meta = await run_quiz_verification_pass(
        build_user_message=build_user,
        system_prompt=system_prompt,
        user_message_kwargs=user_kwargs,
        question_count=qc_question_count,
        graph_node=graph_node,
        pass_label=pass_label,
    )
    new_attempt = current_attempt + 1

    if verification is None:
        error_type: QcInfraErrorType = "qc_verification_failed"
        if not verification_meta.get("llm_ok"):
            raw_err = verification_meta.get("llm_error_type")
            if raw_err in (
                "llm_infra_error",
                "rate_limited",
                "token_limit",
                "llm_key_pool_exhausted",
            ):
                error_type = cast(QcInfraErrorType, raw_err)
        elif not verification_meta.get("parse_ok"):
            error_type = "qc_extraction_failed"
        logger.warning(
            "Quiz QC verification failed on attempt %d/%d — %s",
            new_attempt,
            MAX_QC_ATTEMPTS,
            verification_meta.get("llm_error_type") or "parse_failed",
        )
        infra_return = qc_infra_failure_return(
            new_attempt=new_attempt,
            error_type=error_type,
            provider_meta=verification_meta.get("provider_meta"),
            retry_after_seconds=verification_meta.get("retry_after_seconds"),
            next_llm_retry_at=verification_meta.get("next_llm_retry_at"),
            suggestion=verification_meta.get("suggestion"),
        )
        infra_qc_result = infra_return.get("qc_result") or {}
        qc_pass_decision = build_qc_pass_decision(
            qc_passed=False,
            qc_result=infra_qc_result,
            routing_mode="none",
            det_checks=det_checks,
        )
        log_qc_artifacts(
            state,
            verification=None,
            verification_meta=verification_meta,
            qc_result=infra_qc_result,
            qc_passed=False,
            qc_pass_decision=qc_pass_decision,
            routing=QuizRetryRoutingResult(mode="none"),
        )
        return infra_return

    model_used = verification_meta.get("llm_model_used") or llm_settings.qc_llm_model

    if is_targeted and prior_qc_result is not None:
        merged_checks = merge_targeted_qc_checks(
            prior_qc_result,
            verification,
            reverify_question_ids=list(state.get("qc_reverify_question_ids") or []),
        )
        verification_for_build = {**verification, "checks": merged_checks}
    elif frozen_ids and prior_qc_result is not None:
        merged_checks = merge_targeted_qc_checks(
            prior_qc_result,
            verification,
            reverify_question_ids=reverify_for_merge,
        )
        verification_for_build = {**verification, "checks": merged_checks}
    else:
        verification_for_build = verification

    qc_result = build_final_quiz_qc_result(
        verification_for_build,
        det_checks,
        questions=validated,
        model=model_used,
    )
    qc_result["verification_mode"] = verification_mode

    routing = classify_quiz_retry_routing(qc_result, validated)
    passed = is_quiz_qc_deliverable(
        overall_status=qc_result["overall_status"],
        failed_checks=qc_result.get("failed_checks") or [],
        wrong_answer_risk=qc_result.get("wrong_answer_risk", "none"),
        retry_recommendation=qc_result.get("retry_recommendation"),
    )

    logger.info(
        "Quiz QC attempt %d/%d — mode=%s status=%s, risk=%s, retry=%s",
        new_attempt,
        MAX_QC_ATTEMPTS,
        verification_mode,
        qc_result.get("overall_status"),
        qc_result.get("wrong_answer_risk", "?"),
        routing.mode,
    )

    qc_pass_decision = build_qc_pass_decision(
        qc_passed=passed,
        qc_result=qc_result,
        routing_mode=routing.mode,
        det_checks=det_checks,
    )
    log_qc_artifacts(
        state,
        verification=verification_for_build,
        verification_meta=verification_meta,
        qc_result=qc_result,
        qc_passed=passed,
        qc_pass_decision=qc_pass_decision,
        routing=routing,
    )

    frozen_question_ids: list[str] | None = None
    if not is_targeted:
        frozen_question_ids = accumulate_frozen_question_ids(
            qc_result.get("checks", []),
            state.get("qc_frozen_question_ids"),
        )

    base_return: dict[str, Any] = {
        "qc_attempt": new_attempt,
        "qc_result": qc_result,
        "qc_verification_mode": verification_mode,
        "qc_retry_mode": routing.mode,
        "qc_reverify_question_ids": routing.failed_question_ids,
        "qc_missing_concepts": routing.missing_concepts,
        "qc_question_failures": routing.question_failures,
        "qc_frozen_question_ids": frozen_question_ids,
        "fixed_questions": None,
    }

    if passed:
        return {
            **base_return,
            "qc_passed": True,
            "qc_feedback": "",
            "qc_failed_permanently": False,
            "qc_retry_mode": "none",
        }

    feedback = format_qc_feedback(qc_result)
    permanently_failed = new_attempt >= MAX_QC_ATTEMPTS

    if permanently_failed:
        logger.warning(
            "Quiz QC permanently failed after %d attempts for node '%s'",
            MAX_QC_ATTEMPTS,
            state.get("node_title"),
        )

    return {
        **base_return,
        "qc_passed": False,
        "qc_feedback": feedback,
        "qc_failed_permanently": permanently_failed,
    }
