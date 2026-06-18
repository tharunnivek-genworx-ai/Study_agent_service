# src/api/control/study_agent/nodes/quality_check_node.py
"""Evaluate generated study material quality via a dedicated LLM call."""

from __future__ import annotations

import json
import logging
from typing import Any, cast

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig

from src.api.config.dbconfig import settings
from src.api.control.study_agent.prompts import quality_checker_prompt
from src.api.control.study_agent.states.state import StudyMaterialGraphState
from src.api.utils.LLM_utils.groq_retry import invoke_llm_rotating

logger = logging.getLogger(__name__)

MAX_QC_ATTEMPTS = 3

_DEFAULT_INSTRUCTION = (
    "No specific teaching instruction provided. Write for a new IT hire "
    "who knows basic programming but is unfamiliar with the topic."
)


def _should_skip_qc(state: StudyMaterialGraphState) -> bool:
    """Skip QC for vague responses during improve/regenerate tasks.

    Vague responses are status messages to the mentor (not study material),
    so there is nothing meaningful to quality-check.
    """
    mode = state.get("generation_mode") or "generate"

    if mode == "improve" and state.get("improve_status") == "vague":
        return True
    if mode == "regenerate" and state.get("regenerate_status") == "vague":
        return True

    return False


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
        return cast(dict[str, Any], json.loads(text))
    except json.JSONDecodeError:
        logger.warning("QC response was not valid JSON: %.200s", text)
        return None


def format_qc_feedback(qc_result: dict[str, Any]) -> str:
    """Build a human-readable feedback string from the QC result for retry."""
    parts: list[str] = []

    status = qc_result.get("overall_status", "unknown")
    parts.append(f"Quality Check Status: {status.upper()}")

    risk = qc_result.get("hallucination_risk", "unknown")
    parts.append(f"Hallucination Risk: {risk}")

    scores = qc_result.get("scores", {})
    if scores:
        score_lines = [f"  - {k}: {v}" for k, v in scores.items() if v is not None]
        if score_lines:
            parts.append("Scores:\n" + "\n".join(score_lines))

    issues = qc_result.get("issues", [])
    if issues:
        issue_lines = [f"  - {issue}" for issue in issues]
        parts.append("Issues Found:\n" + "\n".join(issue_lines))

    corrective = qc_result.get("corrective_instructions", "")
    if corrective:
        parts.append(f"Corrective Instructions: {corrective}")

    return "\n\n".join(parts)


async def quality_check_node(
    state: StudyMaterialGraphState,
    config: RunnableConfig,
) -> dict[str, Any]:
    """Run quality check on the generated study material.

    Returns qc_passed=True when:
    - QC should be skipped (vague responses)
    - QC evaluation passes
    - QC infrastructure fails (fail-open to avoid blocking delivery)

    Returns qc_passed=False when QC evaluation returns warn or fail.
    Increments qc_attempt on every evaluation.
    Sets qc_failed_permanently=True when max attempts exhausted and still failing.
    """
    current_attempt = state.get("qc_attempt") or 0

    # ── Skip QC for vague improve/regenerate responses ──────────
    if _should_skip_qc(state):
        logger.info("Skipping QC: vague %s response", state.get("generation_mode"))
        return {
            "qc_passed": True,
            "qc_result": None,
            "qc_feedback": "",
            "qc_attempt": current_attempt,
            "qc_failed_permanently": False,
        }

    # ── Skip QC if there's an error or no generated content ─────
    if state.get("error") or not state.get("generated_content"):
        logger.info("Skipping QC: error or no generated content")
        return {
            "qc_passed": True,
            "qc_result": None,
            "qc_feedback": "",
            "qc_attempt": current_attempt,
            "qc_failed_permanently": False,
        }

    # ── Build QC prompt ─────────────────────────────────────────
    teaching_instruction = state.get("effective_instruction") or _DEFAULT_INSTRUCTION

    user_message = quality_checker_prompt.USER_MESSAGE_TEMPLATE.format(
        generation_mode=state.get("generation_mode") or "generate",
        topic_title=state.get("node_title") or "",
        teaching_instruction_text=teaching_instruction,
        has_reference_material=str(bool(state.get("has_reference_material"))),
        generated_content=state.get("generated_content") or "",
    )

    messages = [
        SystemMessage(content=quality_checker_prompt.SYSTEM_PROMPT),
        HumanMessage(content=user_message),
    ]

    # ── Call LLM ────────────────────────────────────────────────
    try:
        raw_response, _, _ = await invoke_llm_rotating(
            messages=messages,
            model=settings.llm_model,
            temperature=0.0,
            timeout=90,
        )
    except Exception as exc:
        logger.exception("QC LLM call failed — defaulting to pass (fail-open)")
        return {
            "qc_passed": True,
            "qc_result": None,
            "qc_feedback": "",
            "qc_attempt": current_attempt + 1,
            "qc_failed_permanently": False,
            "error": f"Quality check LLM call failed (content accepted): {exc}",
        }

    # ── Parse response ──────────────────────────────────────────
    qc_result = _parse_qc_response(raw_response)
    new_attempt = current_attempt + 1

    if qc_result is None:
        logger.warning("QC JSON parse failed — defaulting to pass (fail-open)")
        return {
            "qc_passed": True,
            "qc_result": None,
            "qc_feedback": "",
            "qc_attempt": new_attempt,
            "qc_failed_permanently": False,
        }

    overall_status = qc_result.get("overall_status", "fail")
    is_refusal = qc_result.get("is_refusal", False)
    passed = overall_status == "pass" or is_refusal is True

    logger.info(
        "QC attempt %d/%d — status=%s, refusal=%s, risk=%s",
        new_attempt,
        MAX_QC_ATTEMPTS,
        overall_status,
        is_refusal,
        qc_result.get("hallucination_risk", "?"),
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
            "QC permanently failed after %d attempts for topic '%s'",
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
