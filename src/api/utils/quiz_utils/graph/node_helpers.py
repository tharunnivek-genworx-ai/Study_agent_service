"""Helpers for quiz generation graph nodes — parsing, LLM calls, and QC state.

Pipeline position
-----------------
Shared utilities imported by quiz graph nodes (``quiz_generator_node``,
``quality_check_node``, rework nodes, etc.). Not graph nodes themselves.

Responsibilities
----------------
- Extract ``AsyncSession`` from LangGraph ``RunnableConfig``.
- Groq LLM calls and JSON question parsing with failure payloads.
- QC retry orchestration (patch/insert prompts, merge logic).
- Artifact logging and QC pass/fail decision shaping for persistence.
"""

from __future__ import annotations

import json
import re
from collections.abc import Awaitable, Callable
from typing import Any, cast

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.config import llm_settings
from src.api.control.quiz_agent.prompts import (
    question_insert_prompt,
    question_prune_prompt,
    question_rework_prompt,
)
from src.api.control.quiz_agent.states.quiz_graph.quiz_state import QuizGraphState
from src.api.schemas.common import QcInfraErrorType
from src.api.schemas.qc_schemas import QuizRetryRoutingResult
from src.api.utils.LLM_utils.groq_quiz_generation_client import (
    call_groq_quiz_generation,
)
from src.api.utils.LLM_utils.llm_failure_diagnostics import (
    build_llm_failure_qc_result,
    build_qc_infra_error_result,
)
from src.api.utils.quiz_utils.artifacts.quiz_artifacts import log_quiz_agent
from src.api.utils.quiz_utils.generation.question_parsing import (
    normalize_parsed_items,
    parse_json_array,
)
from src.api.utils.quiz_utils.graph.constants import MAX_QC_ATTEMPTS
from src.api.utils.quiz_utils.quality_check_utils.document.question_merge import (
    insert_questions,
    prepare_question_patches_for_merge,
    prune_questions_to_count,
    remove_questions_by_ids,
)
from src.api.utils.quiz_utils.quality_check_utils.infra.artifact_logging import (
    log_qc_agent,
)
from src.api.utils.quiz_utils.quality_check_utils.infra.artifact_logging import (
    pipeline_attempt as quiz_pipeline_attempt,
)
from src.api.utils.quiz_utils.quality_check_utils.results.quiz_scoring import (
    extract_failed_checks,
    missing_concepts_from_recommendation,
)

LlmCall = Callable[..., Awaitable[Any]]


def _strip_json_fences(raw: str) -> str:
    text = (raw or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
    return text.strip()


def graph_session(config: RunnableConfig) -> AsyncSession:
    """Pull the AsyncSession passed into the graph invocation config."""
    return cast(AsyncSession, config["configurable"]["session"])


def qc_retry_mode(state: QuizGraphState) -> str:
    """Return the active QC retry mode from state (defaults to ``"none"``)."""
    return state.get("qc_retry_mode") or "none"


def format_gen_feedback_from_checks(failed_checks: list[dict[str, Any]]) -> str:
    """Format deterministic check failures into feedback for the generator retry prompt."""
    lines: list[str] = []
    for check in failed_checks:
        lines.append(
            f"- [{check.get('severity', '?')}] {check.get('category', '?')}/"
            f"{check.get('id', '?')}: {check.get('evidence', '')}"
        )
        hint = (check.get("corrective_hint") or "").strip()
        if hint:
            lines.append(f"  Fix: {hint}")
    return "Structural validation failed:\n" + "\n".join(lines)


async def call_quiz_llm(
    *,
    system_prompt: str,
    user_message: str,
    question_count: int = 1,
    graph_node: str = "quiz_generator",
) -> Any:
    """Invoke the configured Groq model for quiz generation with rotation/retry."""
    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_message),
    ]
    return await call_groq_quiz_generation(
        messages=messages,
        question_count=question_count,
        graph_node=graph_node,
    )


class QuestionCallError(Exception):
    """Raised internally when an LLM call or parse fails during question retry.

    ``payload`` is a partial state dict returned directly to the graph.
    """

    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload
        super().__init__("question LLM call failed")


async def call_and_parse_questions(
    state: QuizGraphState,
    *,
    call_llm: LlmCall,
    system_prompt: str,
    user_message: str,
    generation_type: str,
) -> tuple[list[dict[str, Any]], Any, str, int | None, list[str]]:
    """Call LLM, parse JSON array, normalize items; raise ``QuestionCallError`` on failure.

    Returns ``(parsed_questions, raw_result, model_name, token_usage, hints_stale_ids)``.
    """
    result = await call_llm(system_prompt=system_prompt, user_message=user_message)
    if not result.ok:
        raise QuestionCallError(
            {
                "terminal_llm_failure": True,
                "llm_error_type": result.error_type,
                "provider_meta": result.provider_meta,
                "next_llm_retry_at": result.next_llm_retry_at,
                "qc_failed_permanently": True,
                "qc_result": build_llm_failure_qc_result(result),
                "validated_questions": [],
                "quiz_title": f"{state.get('node_title') or 'Quiz'} — Quiz",
            }
        )

    llm_model_used = result.model or llm_settings.llm_model
    raw_content = result.content or ""
    try:
        items = parse_json_array(raw_content)
    except Exception as exc:  # noqa: BLE001
        raise QuestionCallError(
            {
                "error": f"{generation_type} returned invalid JSON: {exc}",
                "raw_llm_output": raw_content,
                "llm_model_used": llm_model_used,
                "token_usage": result.token_usage,
            }
        ) from exc

    parsed, hints_stale_ids = normalize_parsed_items(items)
    return (
        parsed,
        result,
        llm_model_used,
        result.token_usage,
        hints_stale_ids,
    )


def build_question_patch_messages(
    state: QuizGraphState,
    questions: list[dict[str, Any]],
) -> tuple[str, str]:
    """Build system/user messages for QC-driven question patch retry."""
    user_message = question_rework_prompt.build_user_message(
        topic_title=state.get("node_title") or "",
        study_material_content=state.get("study_material_content") or "",
        difficulty_profile=state.get("difficulty") or "mixed",
        question_failures=state.get("qc_question_failures") or [],
        questions=questions,
        domain=state.get("domain"),
        topic_split=state.get("topic_split"),
    )
    return (
        question_rework_prompt.build_system_prompt(domain=state.get("domain")),
        user_message,
    )


def build_question_insert_messages(
    state: QuizGraphState,
    questions: list[dict[str, Any]],
) -> tuple[str, str]:
    """Build system/user messages for inserting questions to cover missing concepts."""
    user_message = question_insert_prompt.build_user_message(
        topic_title=state.get("node_title") or "",
        study_material_content=state.get("study_material_content") or "",
        difficulty_profile=state.get("difficulty") or "mixed",
        missing_concepts=state.get("qc_missing_concepts") or [],
        existing_questions=questions,
        domain=state.get("domain"),
        topic_split=state.get("topic_split"),
    )
    return (
        question_insert_prompt.build_system_prompt(domain=state.get("domain")),
        user_message,
    )


def build_question_prune_messages(
    state: QuizGraphState,
    questions: list[dict[str, Any]],
    *,
    remove_count: int,
) -> tuple[str, str]:
    """Build system/user messages for overflow prune (drop unaligned extras)."""
    required_count = int(state.get("question_count") or 0)
    extra_command = (state.get("gen_feedback") or "").strip() or (
        "There are extra questions beyond the requested count. Remove the ones "
        "that are not needed and not aligned with the study material."
    )
    user_message = question_prune_prompt.build_user_message(
        topic_title=state.get("node_title") or "",
        study_material_content=state.get("study_material_content") or "",
        difficulty_profile=state.get("difficulty") or "mixed",
        required_count=required_count,
        remove_count=remove_count,
        existing_questions=questions,
        domain=state.get("domain"),
        topic_split=state.get("topic_split"),
        extra_command=extra_command,
    )
    return (
        question_prune_prompt.build_system_prompt(domain=state.get("domain")),
        user_message,
    )


def _parse_remove_question_ids(raw_content: str) -> list[str]:
    """Parse prune LLM JSON into a list of question ids to remove."""
    text = _strip_json_fences(raw_content)
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid prune JSON: {exc}") from exc

    if isinstance(payload, dict):
        ids = payload.get("remove_question_ids") or payload.get("question_ids") or []
        if isinstance(ids, list):
            return [str(item).strip() for item in ids if str(item).strip()]
        raise ValueError("Expected remove_question_ids array in prune JSON.")

    if isinstance(payload, list):
        remove_ids: list[str] = []
        for item in payload:
            if isinstance(item, str) and item.strip():
                remove_ids.append(item.strip())
            elif isinstance(item, dict):
                question_id = str(item.get("question_id", "")).strip()
                if question_id:
                    remove_ids.append(question_id)
        return remove_ids

    raise ValueError("Expected JSON object or array for prune response.")


async def run_question_prune(
    state: QuizGraphState,
    *,
    call_llm: LlmCall,
) -> dict[str, Any]:
    """Remove surplus questions so the quiz matches ``question_count``.

    After a successful prune, sets ``present_without_qc`` so the graph persists
    the draft without re-entering quality check.
    """
    questions = list(
        state.get("validated_questions") or state.get("parsed_questions") or []
    )
    if not questions:
        return {"error": "Cannot prune quiz questions without an existing quiz."}

    expected_count = int(state.get("question_count") or 0)
    if expected_count <= 0:
        return {"error": "Cannot prune without a positive question_count."}

    if len(questions) <= expected_count:
        return {
            "parsed_questions": questions,
            "validated_questions": questions,
            "qc_retry_mode": "none",
            "present_without_qc": True,
            "qc_passed": True,
            "qc_failed_permanently": False,
            "fixed_questions": None,
            "gen_feedback": "",
            "error": None,
        }

    remove_count = len(questions) - expected_count
    prefer_remove_ids = list(state.get("qc_reverify_question_ids") or [])
    system_prompt, user_message = build_question_prune_messages(
        state,
        questions,
        remove_count=remove_count,
    )

    result = await call_llm(
        system_prompt=system_prompt,
        user_message=user_message,
        question_count=remove_count,
        graph_node="quiz_generator",
    )
    llm_model_used = getattr(result, "model", None) or llm_settings.llm_model
    token_usage = getattr(result, "token_usage", None)
    raw_content = getattr(result, "content", None) or ""

    pruned = questions
    if getattr(result, "ok", False):
        try:
            remove_ids = _parse_remove_question_ids(raw_content)
            existing_ids = {
                str(q.get("question_id", "")).strip()
                for q in questions
                if str(q.get("question_id", "")).strip()
            }
            valid_remove_ids = [qid for qid in remove_ids if qid in existing_ids]
            if valid_remove_ids:
                candidate = remove_questions_by_ids(questions, valid_remove_ids)
                if len(candidate) == expected_count:
                    pruned = candidate
                elif len(candidate) > expected_count:
                    pruned = prune_questions_to_count(
                        candidate,
                        expected_count,
                        prefer_remove_ids=prefer_remove_ids,
                    )
                else:
                    # Too many removed — fall back to deterministic prune from original.
                    pruned = prune_questions_to_count(
                        questions,
                        expected_count,
                        prefer_remove_ids=prefer_remove_ids + valid_remove_ids,
                    )
            else:
                pruned = prune_questions_to_count(
                    questions,
                    expected_count,
                    prefer_remove_ids=prefer_remove_ids,
                )
        except Exception:  # noqa: BLE001
            pruned = prune_questions_to_count(
                questions,
                expected_count,
                prefer_remove_ids=prefer_remove_ids,
            )
    else:
        pruned = prune_questions_to_count(
            questions,
            expected_count,
            prefer_remove_ids=prefer_remove_ids,
        )

    if len(pruned) != expected_count:
        pruned = prune_questions_to_count(
            questions,
            expected_count,
            prefer_remove_ids=prefer_remove_ids,
        )

    return {
        "parsed_questions": pruned,
        "validated_questions": pruned,
        "fixed_questions": None,
        "raw_llm_output": raw_content,
        "llm_model_used": llm_model_used,
        "token_usage": token_usage,
        "quiz_title": f"{state.get('node_title') or 'Quiz'} — Quiz",
        "qc_retry_mode": "none",
        "present_without_qc": True,
        "qc_passed": True,
        "qc_failed_permanently": False,
        "prune_attempt": int(state.get("prune_attempt") or 0) + 1,
        "gen_feedback": "",
        "struct_validation_passed": True,
        "error": None,
    }


async def run_question_retry(
    state: QuizGraphState,
    retry_mode: str,
    *,
    call_llm: LlmCall,
) -> dict[str, Any]:
    """Run surgical QC retry (patch and/or insert) without full regeneration.

    Called from ``quiz_generator_node`` when ``qc_retry_mode`` is in
    ``QUESTION_RETRY_MODES``. Updates ``parsed_questions``, ``validated_questions``,
    and ``fixed_questions`` for targeted QC on the next pass.
    """
    questions = list(
        state.get("validated_questions") or state.get("parsed_questions") or []
    )
    if not questions:
        return {"error": "Cannot run question retry without existing quiz questions."}

    fixed_questions: list[dict[str, Any]] = []
    merged_questions = questions
    llm_model_used = llm_settings.llm_model
    token_usage: int | None = 0
    last_result: Any = None
    hints_stale_ids: list[str] = list(state.get("hints_stale_question_ids") or [])

    try:
        if retry_mode in ("question_patch", "question_patch_then_insert"):
            system_prompt, user_message = build_question_patch_messages(
                state, merged_questions
            )
            (
                patch_questions,
                patch_result,
                patch_model,
                patch_tokens,
                patch_stale,
            ) = await call_and_parse_questions(
                state,
                call_llm=call_llm,
                system_prompt=system_prompt,
                user_message=user_message,
                generation_type="question_patch",
            )
            target_question_ids = list(state.get("qc_reverify_question_ids") or [])
            merged_questions = prepare_question_patches_for_merge(
                merged_questions,
                patch_questions,
                target_question_ids=target_question_ids,
            )
            applied_ids = {
                str(question_id).strip()
                for question_id in target_question_ids
                if str(question_id).strip()
            }
            fixed_questions.extend(
                question
                for question in merged_questions
                if str(question.get("question_id", "")).strip() in applied_ids
            )
            hints_stale_ids.extend(patch_stale)
            hints_stale_ids.extend(applied_ids)
            last_result = patch_result
            llm_model_used = patch_model
            if patch_tokens is not None:
                token_usage = (token_usage or 0) + patch_tokens

        if retry_mode in ("question_insert", "question_patch_then_insert"):
            system_prompt, user_message = build_question_insert_messages(
                state, merged_questions
            )
            (
                insert_questions_raw,
                insert_result,
                insert_model,
                insert_tokens,
                insert_stale,
            ) = await call_and_parse_questions(
                state,
                call_llm=call_llm,
                system_prompt=system_prompt,
                user_message=user_message,
                generation_type="question_insert",
            )
            fixed_questions.extend(insert_questions_raw)
            hints_stale_ids.extend(insert_stale)
            last_result = insert_result
            llm_model_used = insert_model
            if insert_tokens is not None:
                token_usage = (token_usage or 0) + insert_tokens

            merged_questions = insert_questions(merged_questions, insert_questions_raw)

    except QuestionCallError as exc:
        return exc.payload

    expected_count = int(state.get("question_count") or 0)
    overflow = expected_count > 0 and len(merged_questions) > expected_count
    result: dict[str, Any] = {
        "parsed_questions": merged_questions,
        "validated_questions": merged_questions,
        "fixed_questions": fixed_questions,
        "hints_stale_question_ids": list(dict.fromkeys(hints_stale_ids)),
        "raw_llm_output": last_result.content if last_result else "",
        "llm_model_used": llm_model_used,
        "token_usage": token_usage,
        "quiz_title": f"{state.get('node_title') or 'Quiz'} — Quiz",
        # Do not reset gen_attempt — structural retries must still terminate.
        "gen_feedback": "",
        "error": None,
    }
    if overflow:
        # Clear validated so deterministic_validate sees overflow via parsed_questions
        # and routes to question_prune (do not re-enter insert).
        result["validated_questions"] = []
    return result


def log_quiz_artifact(
    state: QuizGraphState,
    agent: str,
    payload: dict[str, Any],
) -> None:
    """Log a quiz pipeline artifact when ``artifact_run_id`` is present in state."""
    run_id = state.get("artifact_run_id")
    if not run_id:
        return
    log_quiz_agent(
        topic_title=state.get("node_title") or str(state.get("node_id")),
        run_id=run_id,
        agent=agent,
        payload=payload,
        pipeline_attempt=quiz_pipeline_attempt(state),
        node_id=str(state.get("node_id") or ""),
        mode=state.get("mode") or "generate",
    )


def build_qc_pass_decision(
    *,
    qc_passed: bool,
    qc_result: dict[str, Any],
    routing_mode: str,
    det_checks: list[dict[str, Any]],
) -> dict[str, Any]:
    """Summarize QC outcome for artifact logs and downstream routing decisions."""
    failed_checks = extract_failed_checks(qc_result.get("checks") or [])
    failed_det = [c for c in det_checks if not c.get("passed", True)]
    retry_recommendation = qc_result.get("retry_recommendation") or {}
    missing_concepts = missing_concepts_from_recommendation(retry_recommendation)
    block_reason: str | None = None

    if not qc_passed:
        if any(not c.get("passed", True) for c in det_checks):
            block_reason = "det_check_fail"
        elif qc_result.get("qcInfraError"):
            block_reason = (
                "truncated_qc"
                if qc_result.get("error_type") == "qc_extraction_failed"
                else "qc_infra_error"
            )
        elif missing_concepts and (
            failed_checks or str(retry_recommendation.get("mode") or "none") != "none"
        ):
            block_reason = "missing_concepts_gate"
        elif failed_checks:
            block_reason = "failed_checks"
        elif qc_result.get("overall_status") == "fail":
            block_reason = "overall_fail"

    return {
        "qc_passed": qc_passed,
        "overall_status": qc_result.get("overall_status"),
        "wrong_answer_risk": qc_result.get("wrong_answer_risk"),
        "failed_check_count": len(failed_checks),
        "failed_det_check_count": len(failed_det),
        "missing_concepts": missing_concepts,
        "retry_mode": routing_mode,
        "block_reason": block_reason,
    }


def qc_infra_failure_return(
    *,
    new_attempt: int,
    error_type: QcInfraErrorType = "qc_verification_failed",
    provider_meta: dict[str, Any] | None = None,
    retry_after_seconds: int | None = None,
    next_llm_retry_at: Any = None,
    suggestion: str | None = None,
) -> dict[str, Any]:
    """Return QC infra failure state — capped at MAX_QC_ATTEMPTS (never infinite loop)."""
    permanently_failed = new_attempt >= MAX_QC_ATTEMPTS
    infra_qc_result = build_qc_infra_error_result(
        provider_meta=provider_meta,
        retry_after_seconds=retry_after_seconds,
        next_llm_retry_at=next_llm_retry_at,
        error_type=error_type,
        suggestion=suggestion,
    )
    return {
        "qc_passed": False,
        "qc_result": infra_qc_result,
        "qc_feedback": "",
        "qc_attempt": new_attempt,
        "qc_failed_permanently": permanently_failed,
        "next_llm_retry_at": next_llm_retry_at,
    }


def resolve_qc_result_for_persist(
    state: QuizGraphState,
) -> tuple[bool, dict[str, Any] | None]:
    """Return ``(qc_failed_permanently, qc_result_dict)`` for DB persistence."""
    if state.get("terminal_llm_failure"):
        return True, state.get("qc_result")

    # Overflow prune presented without another QC pass — treat as deliverable.
    if state.get("present_without_qc") and state.get("qc_passed"):
        return False, None

    qc_failed_permanently = bool(state.get("qc_failed_permanently"))
    raw = state.get("qc_result")

    if qc_failed_permanently and isinstance(raw, dict):
        return True, raw

    if isinstance(raw, dict) and raw.get("qcInfraError"):
        return False, raw

    if qc_failed_permanently:
        return True, raw if isinstance(raw, dict) else None

    return False, None


def log_qc_artifacts(
    state: QuizGraphState,
    *,
    verification: dict[str, Any] | None,
    verification_meta: dict[str, Any],
    qc_result: dict[str, Any] | None,
    qc_passed: bool,
    qc_pass_decision: dict[str, Any],
    routing: QuizRetryRoutingResult,
) -> None:
    """Write QC verification and result artifacts for the current pipeline attempt."""
    attempt = quiz_pipeline_attempt(state)
    log_qc_agent(
        state,
        agent="quiz_qc_verification",
        pipeline_attempt=attempt,
        payload={
            "verification": verification,
            "verification_meta": verification_meta,
            "qc_verification_mode": state.get("qc_verification_mode"),
        },
    )
    log_qc_agent(
        state,
        agent="quiz_qc_result",
        pipeline_attempt=attempt,
        payload={
            "qc_result": qc_result,
            "qc_passed": qc_passed,
            "qc_pass_decision": qc_pass_decision,
            "routing": {
                "mode": routing.mode,
                "failed_question_ids": routing.failed_question_ids,
                "missing_concepts": routing.missing_concepts,
            },
            "verification_meta": verification_meta,
        },
    )
