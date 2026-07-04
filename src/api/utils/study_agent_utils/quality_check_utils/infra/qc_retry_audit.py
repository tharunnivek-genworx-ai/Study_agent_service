"""Build unified QC retry audit payloads for artifact logging."""

from __future__ import annotations

from typing import Any, Literal

from src.api.control.study_agent.states.state import StudyMaterialGraphState
from src.api.schemas.qc_schemas import RetryRoutingResult
from src.api.utils.study_agent_utils.quality_check_utils.results.feedback import (
    format_qc_feedback,
)

SECTION_RETRY_MODES = frozenset(
    {"section_patch", "section_insert", "section_patch_then_insert"}
)

RetryFeedbackChannel = Literal[
    "structured_section_failures", "flat_qc_feedback", "none"
]


def retry_feedback_channel(mode: str) -> RetryFeedbackChannel:
    """Map retry routing mode to the feedback channel study_agent consumes."""
    if mode in SECTION_RETRY_MODES:
        return "structured_section_failures"
    if mode == "full_regeneration":
        return "flat_qc_feedback"
    return "none"


def build_retry_routing_snapshot(routing: RetryRoutingResult) -> dict[str, Any]:
    """Serialize routing decision for artifact persistence."""
    return {
        "mode": routing.mode,
        "failed_section_ids": routing.failed_section_ids,
        "missing_checklist_ids": routing.missing_checklist_ids,
        "section_failures": routing.section_failures,
        "rationale": routing.rationale,
    }


def empty_retry_routing_snapshot() -> dict[str, Any]:
    """Routing snapshot when retry routing is unavailable (infra/inconclusive)."""
    return {
        "mode": "none",
        "failed_section_ids": [],
        "missing_checklist_ids": [],
        "section_failures": [],
        "rationale": "",
    }


def build_qc_retry_context(
    *,
    qc_result: dict[str, Any],
    routing: RetryRoutingResult | None,
    passed: bool,
    qc_attempt: int,
    pipeline_attempt: int,
) -> dict[str, Any]:
    """Build retry audit fields embedded in ``05_qc_result.json`` artifacts."""
    if passed or routing is None:
        channel: RetryFeedbackChannel = "none"
        feedback = ""
        routing_snapshot = empty_retry_routing_snapshot()
        next_study_attempt = None
    else:
        channel = retry_feedback_channel(routing.mode)
        feedback = format_qc_feedback(qc_result)
        routing_snapshot = build_retry_routing_snapshot(routing)
        next_study_attempt = pipeline_attempt + 1

    return {
        "qc_attempt": qc_attempt,
        "pipeline_attempt": pipeline_attempt,
        "retry_feedback_channel": channel,
        "prompt_channel": {
            "structured_section_failures": channel == "structured_section_failures",
            "flat_qc_feedback": channel == "flat_qc_feedback",
        },
        "qc_feedback": feedback,
        "retry_routing": routing_snapshot,
        "next_study_pipeline_attempt": next_study_attempt,
    }


def build_qc_result_log_payload(
    *,
    qc_result: dict[str, Any],
    routing: RetryRoutingResult | None,
    passed: bool,
    qc_attempt: int,
    pipeline_attempt: int,
    **base_fields: Any,
) -> dict[str, Any]:
    """Merge standard QC result artifact fields with unified retry audit context."""
    return {
        **base_fields,
        "qc_result": qc_result,
        **build_qc_retry_context(
            qc_result=qc_result,
            routing=routing,
            passed=passed,
            qc_attempt=qc_attempt,
            pipeline_attempt=pipeline_attempt,
        ),
    }


def build_study_retry_input_audit(state: StudyMaterialGraphState) -> dict[str, Any]:
    """Snapshot of retry inputs study_agent consumed when building prompts."""
    retry_mode = state.get("qc_retry_mode") or "none"
    channel = retry_feedback_channel(retry_mode)
    qc_feedback = (state.get("qc_feedback") or "").strip()
    failed_db = (state.get("failed_qc_feedback") or "").strip()
    section_failures = state.get("qc_section_failures") or []
    qc_attempt = state.get("qc_attempt") or 0

    return {
        "triggered_by_qc_attempt": qc_attempt,
        "qc_retry_mode": retry_mode,
        "retry_feedback_channel": channel,
        "feedback_blocks": {
            "quality_check_feedback": bool(
                channel == "flat_qc_feedback" and qc_feedback
            ),
            "previous_failed_quality_check_feedback": bool(failed_db),
            "sections_to_fix": len(section_failures),
        },
        "retry_input": {
            "qc_reverify_section_ids": state.get("qc_reverify_section_ids") or [],
            "qc_missing_checklist_ids": state.get("qc_missing_checklist_ids") or [],
            "qc_section_failures": section_failures,
            "qc_feedback": qc_feedback,
            "failed_qc_feedback": failed_db or None,
            "failed_qc_feedback_source": "db_hydration" if failed_db else None,
            "in_run_qc_feedback_source": "pipeline_qc_fail" if qc_feedback else None,
        },
    }


def should_attach_study_retry_audit(state: StudyMaterialGraphState) -> bool:
    """True when this study generation pass is a QC retry or DB-hydrated QC context."""
    if (state.get("qc_attempt") or 0) > 0:
        return True
    if (state.get("failed_qc_feedback") or "").strip():
        return True
    retry_mode = state.get("qc_retry_mode") or "none"
    return retry_mode != "none"


__all__ = [
    "SECTION_RETRY_MODES",
    "RetryFeedbackChannel",
    "build_qc_result_log_payload",
    "build_qc_retry_context",
    "build_retry_routing_snapshot",
    "build_study_retry_input_audit",
    "empty_retry_routing_snapshot",
    "retry_feedback_channel",
    "should_attach_study_retry_audit",
]
