"""Node functions for the quiz draft generation LangGraph (Graph 1).

Every node is a plain async function that receives the running
``QuizGraphState`` and returns a partial state update. DB access goes only
through the existing repository layer; prompt assembly goes only through the
existing prompt builder. The ``AsyncSession`` is threaded in via the graph
invocation config — nodes never create their own session.
"""

from __future__ import annotations

import json
import logging
from typing import Any, cast
from uuid import uuid4

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.config.llm_config import llm_settings
from src.api.control.quiz_agent.prompts.quiz_prompt import build_quiz_prompt
from src.api.control.quiz_agent.states.quiz_state import QuizGraphState
from src.api.core.exceptions.quiz_exceptions.quiz_generation_exceptions import (
    QuizHasNoPublishedStudyMaterialException,
)
from src.api.core.exceptions.quiz_exceptions.trainee_quiz_exceptions import (
    QuizNotFoundException,
)
from src.api.data.repositories.quiz_repositories.quiz_repository import QuizRepository
from src.api.data.repositories.study_agent_repositories.study_material_repository import (  # noqa: E501
    StudyMaterialRepository,
)
from src.api.schemas.common.generation_diagnostics_schema import QcInfraErrorType
from src.api.utils.LLM_utils.groq_retry import call_groq_with_rotation
from src.api.utils.LLM_utils.llm_failure_diagnostics import (
    build_llm_failure_qc_result,
    build_qc_infra_error_result,
)
from src.api.utils.space_node_utils.node_role_assert import (
    _get_node_and_assert_space_access,
)

logger = logging.getLogger(__name__)

_VALID_CORRECT_OPTIONS = {"A", "B", "C", "D"}


# ── Shared helpers ────────────────────────────────────────────────────────


def _session(config: RunnableConfig) -> AsyncSession:
    """Pull the AsyncSession passed into the graph invocation config."""
    return cast(AsyncSession, config["configurable"]["session"])


def _parse_json_array(raw: str) -> list:
    """Parse an LLM response that should be a JSON array.

    Tolerates accidental ```json fences around the payload.
    """
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text
        if text.endswith("```"):
            text = text[: -len("```")]
        text = text.strip()
        if text.lower().startswith("json"):
            text = text[len("json") :].strip()
    parsed = json.loads(text)
    if not isinstance(parsed, list):
        raise ValueError("Expected a JSON array.")
    return parsed


def _empty_to_none(value: Any) -> Any:
    if isinstance(value, str) and value.strip() == "":
        return None
    return value


# ── Nodes ─────────────────────────────────────────────────────────────────


async def load_generation_context(
    state: QuizGraphState, config: RunnableConfig
) -> QuizGraphState:
    session = _session(config)

    # Verify node exists/active and mentor owns its space (raises on failure).
    node = await _get_node_and_assert_space_access(
        session, state["node_id"], state["mentor_id"], owner_only=True
    )

    study_repo = StudyMaterialRepository(session)
    version = await study_repo.get_published_version(state["node_id"])
    if version is None or not (version.content or "").strip():
        version = await study_repo.get_active_version(state["node_id"])
    if version is None or not (version.content or "").strip():
        raise QuizHasNoPublishedStudyMaterialException()

    from uuid import UUID  # noqa: PLC0415

    return {
        **state,
        "space_id": cast(UUID, node.space_id),
        "node_title": cast(str, node.title),
        "study_material_version_id": cast(UUID, version.version_id),
        "study_material_content": cast(str, version.content),
    }


async def load_existing_quiz_if_regenerate(
    state: QuizGraphState, config: RunnableConfig
) -> QuizGraphState:
    if state.get("mode") != "regenerate":
        return state

    session = _session(config)
    repo = QuizRepository(session)

    quiz_id = state.get("quiz_id")
    quiz = await repo.get_quiz_by_id(quiz_id) if quiz_id is not None else None
    if quiz is None or quiz.node_id != state["node_id"]:
        raise QuizNotFoundException()

    questions = await repo.get_active_questions_by_quiz(quiz_id)  # type: ignore[arg-type]
    existing = [
        {
            "question_id": str(q.question_id),
            "question_text": q.question_text,
            "option_a": q.option_a,
            "option_b": q.option_b,
            "option_c": q.option_c,
            "option_d": q.option_d,
            "correct_option": q.correct_option,
            "explanation": q.explanation,
            "order_index": q.order_index,
        }
        for q in questions
    ]

    return {**state, "existing_quiz_questions": existing}


async def build_quiz_prompt_payload(state: QuizGraphState) -> QuizGraphState:
    qc_attempt = state.get("qc_attempt") or 0
    qc_feedback = (state.get("qc_feedback") or "").strip() if qc_attempt > 0 else None
    prompt_input = build_quiz_prompt(
        node_title=state.get("node_title"),
        study_material_content=state.get("study_material_content"),
        question_count=state["question_count"],
        difficulty=state["difficulty"],
        mode=state.get("mode", "generate"),
        existing_quiz_questions=state.get("existing_quiz_questions"),
        mentor_feedback=state.get("mentor_feedback"),
        qc_feedback=qc_feedback,
        failed_qc_feedback=state.get("failed_qc_feedback"),
    )
    return {**state, "prompt_input": prompt_input}


async def invoke_quiz_llm(state: QuizGraphState) -> QuizGraphState:
    prompt_input = state.get("prompt_input")
    if not prompt_input:
        return {**state, "error": "Missing prompt input for quiz generation."}

    result = await call_groq_with_rotation(
        messages=[
            SystemMessage(content=prompt_input["system_prompt"]),
            HumanMessage(content=prompt_input["user_message"]),
        ],
        model=llm_settings.llm_model,
        temperature=0.4,
        timeout=120,
        graph_node="quiz_generator",
    )
    if not result.ok:
        logger.error(
            "Groq quiz generation failed: %s",
            result.error_type,
        )
        return {
            **state,
            "terminal_llm_failure": True,
            "llm_error_type": result.error_type,
            "provider_meta": result.provider_meta,
            "next_llm_retry_at": result.next_llm_retry_at,
            "qc_failed_permanently": True,
            "qc_result": build_llm_failure_qc_result(result),
            "validated_questions": [],
            "quiz_title": f"{state.get('node_title') or 'Quiz'} — Quiz",
        }

    return {
        **state,
        "raw_llm_output": result.content or "",
        "llm_model_used": result.model or llm_settings.llm_model,
        "token_usage": result.token_usage,
    }


async def parse_quiz_output(state: QuizGraphState) -> QuizGraphState:
    raw = state.get("raw_llm_output")
    if not raw:
        return {**state, "error": "No LLM output to parse."}

    try:
        items = _parse_json_array(raw)
    except Exception as exc:  # noqa: BLE001
        return {**state, "error": f"Malformed quiz output: {exc}"}

    parsed: list[dict] = []
    order_index = 0
    for item in items:
        if not isinstance(item, dict):
            return {**state, "error": "Quiz output element is not an object."}

        question_text = item.get("question_text")
        # Skip the optional shortfall marker described in the prompt contract.
        if isinstance(question_text, str) and question_text.startswith(
            "GENERATION NOTE"
        ):
            continue

        for field in (
            "question_text",
            "option_a",
            "option_b",
            "correct_option",
            "explanation",
        ):
            if item.get(field) in (None, ""):
                return {
                    **state,
                    "error": f"Quiz question missing required field: {field}.",
                }

        question_text = item.get("question_text")
        explanation = item.get("explanation")
        opt_a = item.get("option_a")
        opt_b = item.get("option_b")
        opt_c = _empty_to_none(item.get("option_c"))
        opt_d = _empty_to_none(item.get("option_d"))

        parsed.append(
            {
                "question_id": item.get("question_id") or str(uuid4()),
                "question_text": question_text,
                "option_a": opt_a,
                "option_b": opt_b,
                "option_c": opt_c,
                "option_d": opt_d,
                "correct_option": item.get("correct_option"),
                "explanation": explanation,
                "order_index": order_index,
            }
        )
        order_index += 1

    quiz_title = f"{state.get('node_title') or 'Quiz'} — Quiz"
    return {**state, "parsed_questions": parsed, "quiz_title": quiz_title}


async def validate_quiz_structure(state: QuizGraphState) -> QuizGraphState:
    parsed = state.get("parsed_questions") or []

    if len(parsed) != state["question_count"]:
        return {
            **state,
            "error": (
                f"LLM returned {len(parsed)} questions but "
                f"{state['question_count']} were requested. Please try again."
            ),
        }

    seen_texts: set[str] = set()
    for q in parsed:
        option_a = q.get("option_a")
        option_b = q.get("option_b")
        option_c = q.get("option_c")
        option_d = q.get("option_d")
        correct_option = q.get("correct_option")
        explanation = q.get("explanation")
        question_text = q.get("question_text")

        # option_a and option_b must be present and non-empty.
        if not (isinstance(option_a, str) and option_a.strip()):
            return {
                **state,
                "error": "Quiz validation failed: option_a is missing or empty.",
            }
        if not (isinstance(option_b, str) and option_b.strip()):
            return {
                **state,
                "error": "Quiz validation failed: option_b is missing or empty.",
            }

        # option_c / option_d may be None but never an empty string.
        for optional in (option_c, option_d):
            if optional is not None and (
                not isinstance(optional, str) or optional.strip() == ""
            ):
                return {
                    **state,
                    "error": "Quiz validation failed: optional answer is blank.",
                }

        # correct_option must be A-D and map to a non-None option.
        if correct_option not in _VALID_CORRECT_OPTIONS:
            return {
                **state,
                "error": f"Quiz validation failed: invalid correct_option {correct_option!r}.",  # noqa: E501
            }
        option_map = {
            "A": option_a,
            "B": option_b,
            "C": option_c,
            "D": option_d,
        }
        if option_map[correct_option] is None:
            return {
                **state,
                "error": "Quiz validation failed: correct_option points to a missing option.",  # noqa: E501
            }

        # No blank explanations.
        if not (isinstance(explanation, str) and explanation.strip()):
            return {
                **state,
                "error": "Quiz validation failed: explanation is missing or empty.",
            }

        # No duplicate question_text.
        if question_text in seen_texts:
            return {
                **state,
                "error": "Quiz validation failed: duplicate question text.",
            }
        seen_texts.add(question_text)

    return {**state, "validated_questions": parsed}


def _resolve_qc_result_for_persist(
    state: QuizGraphState,
) -> tuple[bool, dict[str, Any] | None]:
    """Return ``(qc_failed_permanently, qc_result_dict)`` for DB persistence."""
    if state.get("terminal_llm_failure"):
        return True, state.get("qc_result")

    qc_failed_permanently = bool(state.get("qc_failed_permanently"))
    raw = state.get("qc_result")

    if qc_failed_permanently and isinstance(raw, dict):
        return True, raw

    if isinstance(raw, dict) and raw.get("qcInfraError"):
        return False, raw

    if qc_failed_permanently:
        return True, raw if isinstance(raw, dict) else None

    return False, None


async def persist_quiz_draft(
    state: QuizGraphState, config: RunnableConfig
) -> QuizGraphState:
    session = _session(config)
    repo = QuizRepository(session)
    validated = state.get("validated_questions") or []

    qc_failed_permanently, qc_result = _resolve_qc_result_for_persist(state)
    next_llm_retry_at = state.get("next_llm_retry_at")
    title = state.get("quiz_title") or "Quiz"
    difficulty = state["difficulty"]

    replace_quiz_id = state.get("quiz_id")
    if replace_quiz_id is not None:
        quiz_id = await repo.replace_quiz_draft_with_questions(
            quiz_id=replace_quiz_id,
            node_id=state["node_id"],
            title=title,
            difficulty=difficulty,
            questions=validated,
            qc_failed_permanently=qc_failed_permanently,
            qc_result=qc_result,
            study_material_version_id=state.get("study_material_version_id"),
            next_llm_retry_at=next_llm_retry_at,
        )
    else:
        quiz_id = await repo.create_quiz_draft_with_questions(
            node_id=state["node_id"],
            space_id=state["space_id"],  # type: ignore[arg-type]
            study_material_version_id=state["study_material_version_id"],  # type: ignore[arg-type]
            title=title,
            difficulty=difficulty,
            created_by=state["mentor_id"],
            questions=validated,
            qc_failed_permanently=qc_failed_permanently,
            qc_result=qc_result,
            next_llm_retry_at=next_llm_retry_at,
        )

    return {**state, "created_quiz_id": quiz_id}


MAX_QC_ATTEMPTS = 3


def _parse_qc_response(raw: str) -> dict[str, Any] | None:
    """Parse the QC JSON response, tolerating markdown fences."""
    text = raw.strip()

    # Strip markdown code fences if present
    if text.startswith("```"):
        first_newline = text.find("\n")
        if first_newline != -1:
            text = text[first_newline + 1 :]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return cast(dict[str, Any], parsed)
        return None
    except json.JSONDecodeError:
        logger.warning("QC response was not valid JSON: %.200s", text)
        return None


def format_qc_feedback(qc_result: dict[str, Any]) -> str:
    """Build a human-readable feedback string from the QC result for retry."""
    parts: list[str] = []

    status = qc_result.get("overall_status", "unknown")
    parts.append(f"Quality Check Status: {status.upper()}")

    risk = qc_result.get("wrong_answer_risk", "unknown")
    parts.append(f"Wrong Answer Risk: {risk}")

    scores = qc_result.get("scores", {})
    if scores:
        score_lines = [f"  - {k}: {v}" for k, v in scores.items() if v is not None]
        if score_lines:
            parts.append("Scores:\n" + "\n".join(score_lines))

    flagged = qc_result.get("flagged_questions", [])
    if flagged:
        flagged_lines = []
        for f in flagged:
            q_num = f.get("question_number", "?")
            flags = ", ".join(f.get("flags", []))
            flagged_lines.append(f"  - Question {q_num}: {flags}")
        parts.append("Flagged Questions:\n" + "\n".join(flagged_lines))

    issues = qc_result.get("issues", [])
    if issues:
        issue_lines = [f"  - {issue}" for issue in issues]
        parts.append("General Issues Found:\n" + "\n".join(issue_lines))

    corrective = qc_result.get("corrective_instructions", "")
    if corrective:
        parts.append(f"Corrective Instructions: {corrective}")

    return "\n\n".join(parts)


async def quality_check_node(
    state: QuizGraphState,
    config: RunnableConfig,
) -> dict[str, Any]:
    """Run quality check on the generated quiz.

    Returns qc_passed=True when:
    - QC evaluation passes
    - QC infrastructure fails (fail-open to avoid blocking delivery)

    Returns qc_passed=False when QC evaluation returns warn or fail.
    Increments qc_attempt on every evaluation.
    Sets qc_failed_permanently=True when max attempts exhausted and still failing.
    """
    current_attempt = state.get("qc_attempt") or 0

    # ── Skip QC on terminal LLM failure (diagnostics already set) ─
    if state.get("terminal_llm_failure"):
        logger.info("Skipping QC: terminal LLM failure")
        return {
            "qc_passed": True,
            "qc_result": state.get("qc_result"),
            "qc_feedback": "",
            "qc_attempt": current_attempt,
            "qc_failed_permanently": bool(state.get("qc_failed_permanently")),
        }

    # ── Skip QC if there's an error or no generated questions ─────
    if state.get("error") or not state.get("validated_questions"):
        logger.info("Skipping QC: error or no generated questions")
        return {
            "qc_passed": True,
            "qc_result": None,
            "qc_feedback": "",
            "qc_attempt": current_attempt,
            "qc_failed_permanently": False,
        }

    # ── Build QC prompt ─────────────────────────────────────────
    from src.api.control.quiz_agent.prompts import quiz_qc_prompt  # noqa: PLC0415

    # Serialize questions to JSON for the LLM
    questions_for_qc = []
    validated_qs = state.get("validated_questions") or []
    for q in validated_qs:
        questions_for_qc.append(
            {
                "question_id": str(q.get("question_id")),
                "question_text": q["question_text"],
                "option_a": q["option_a"],
                "option_b": q["option_b"],
                "option_c": q.get("option_c"),
                "option_d": q.get("option_d"),
                "correct_option": q["correct_option"],
                "explanation": q.get("explanation"),
            }
        )

    user_message = quiz_qc_prompt.USER_MESSAGE_TEMPLATE.format(
        topic_title=state.get("node_title") or "",
        difficulty=state.get("difficulty") or "mixed",
        question_count=len(questions_for_qc),
        generation_mode=state.get("mode") or "generate",
        study_material_content=state.get("study_material_content") or "",
        quiz_questions_json=json.dumps(questions_for_qc, indent=2),
    )

    messages = [
        SystemMessage(content=quiz_qc_prompt.SYSTEM_PROMPT),
        HumanMessage(content=user_message),
    ]

    # ── Call LLM ────────────────────────────────────────────────
    llm_result = await call_groq_with_rotation(
        messages=messages,
        model=llm_settings.qc_llm_model,
        temperature=0.0,
        timeout=90,
        max_tokens=llm_settings.qc_llm_max_tokens,
        graph_node="quality_check",
    )
    new_attempt = current_attempt + 1

    if not llm_result.ok:
        logger.error(
            "Quiz QC LLM call failed (%s) — defaulting to pass (fail-open)",
            llm_result.error_type,
        )
        qc_err_type: QcInfraErrorType = "llm_infra_error"
        if llm_result.error_type in (
            "llm_infra_error",
            "rate_limited",
            "token_limit",
            "llm_key_pool_exhausted",
            "qc_extraction_failed",
            "qc_verification_failed",
        ):
            qc_err_type = cast(QcInfraErrorType, llm_result.error_type)
        infra_qc_result = build_qc_infra_error_result(
            provider_meta=llm_result.provider_meta,
            retry_after_seconds=llm_result.retry_after_seconds,
            next_llm_retry_at=llm_result.next_llm_retry_at,
            error_type=qc_err_type,
        )
        return {
            "qc_passed": True,
            "qc_result": infra_qc_result,
            "qc_feedback": "",
            "qc_attempt": new_attempt,
            "qc_failed_permanently": False,
            "next_llm_retry_at": llm_result.next_llm_retry_at,
        }

    raw_response = llm_result.content or ""

    # ── Parse response ──────────────────────────────────────────
    qc_result = _parse_qc_response(raw_response)

    if qc_result is None:
        logger.warning("Quiz QC JSON parse failed — defaulting to pass (fail-open)")
        infra_qc_result = build_qc_infra_error_result(error_type="llm_infra_error")
        return {
            "qc_passed": True,
            "qc_result": infra_qc_result,
            "qc_feedback": "",
            "qc_attempt": new_attempt,
            "qc_failed_permanently": False,
        }

    overall_status = qc_result.get("overall_status", "fail")
    passed = overall_status == "pass"

    logger.info(
        "Quiz QC attempt %d/%d — status=%s, risk=%s",
        new_attempt,
        MAX_QC_ATTEMPTS,
        overall_status,
        qc_result.get("wrong_answer_risk", "?"),
    )

    if passed:
        return {
            "qc_passed": True,
            "qc_result": qc_result,
            "qc_feedback": "",
            "qc_attempt": new_attempt,
            "qc_failed_permanently": False,
        }

    # ── Failed ──────────────────────────────────────────────────
    feedback = format_qc_feedback(qc_result)
    permanently_failed = new_attempt >= MAX_QC_ATTEMPTS

    if permanently_failed:
        logger.warning(
            "Quiz QC permanently failed after %d attempts for node '%s'",
            MAX_QC_ATTEMPTS,
            state.get("node_title"),
        )

    return {
        "qc_passed": False,
        "qc_result": qc_result,
        "qc_feedback": feedback,
        "qc_attempt": new_attempt,
        "qc_failed_permanently": permanently_failed,
    }
