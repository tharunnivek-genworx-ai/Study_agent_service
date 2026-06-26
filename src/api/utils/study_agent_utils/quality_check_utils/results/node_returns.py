"""Pre-built graph state returns for QC node early exits."""

from __future__ import annotations

from typing import Any

from src.api.control.study_agent.states.state import StudyMaterialGraphState
from src.api.utils.study_agent_utils.quality_check_utils.core.constants import (
    MAX_QC_ATTEMPTS,
)


def build_skip_return(
    state: StudyMaterialGraphState,
    *,
    qc_passed: bool = True,
    qc_result: dict[str, Any] | None = None,
    preserve_terminal: bool = False,
) -> dict[str, Any]:
    current_attempt = state.get("qc_attempt") or 0
    if preserve_terminal:
        return {
            "qc_passed": qc_passed,
            "qc_result": state.get("qc_result") if qc_result is None else qc_result,
            "qc_feedback": "",
            "qc_attempt": current_attempt,
            "qc_failed_permanently": bool(state.get("qc_failed_permanently")),
            "qc_extraction": state.get("qc_extraction"),
        }
    return {
        "qc_passed": qc_passed,
        "qc_result": qc_result,
        "qc_feedback": "",
        "qc_attempt": current_attempt,
        "qc_failed_permanently": False,
        "qc_extraction": None,
    }


def build_invalid_json_return(new_attempt: int) -> dict[str, Any]:
    return {
        "qc_passed": False,
        "qc_result": {
            "overall_status": "fail",
            "is_refusal": False,
            "hallucination_risk": "none",
            "scores": {},
            "checks": [],
            "failed_checks": [],
            "issues": ["Generated content is not valid JSON."],
            "corrective_instructions": "Return only the study document JSON object.",
            "summary": "Invalid JSON from generator.",
        },
        "qc_feedback": "Generated content is not valid JSON.",
        "qc_attempt": new_attempt,
        "qc_failed_permanently": new_attempt >= MAX_QC_ATTEMPTS,
        "qc_extraction": None,
    }
