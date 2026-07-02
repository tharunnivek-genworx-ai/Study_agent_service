"""Pre-built graph state returns for QC node early exits."""

from __future__ import annotations

import logging
from typing import Any

from src.api.control.study_agent.states.state import StudyMaterialGraphState

logger = logging.getLogger(__name__)


def build_qc_guard_return(
    state: StudyMaterialGraphState,
    *,
    reason: str,
) -> dict[str, Any]:
    """Return when QC is invoked for state it should not process (misroute guard)."""
    logger.error("QC guard return: %s", reason)
    current_attempt = state.get("qc_attempt") or 0
    return {
        "qc_passed": False,
        "qc_evaluated": False,
        "qc_result": state.get("qc_result"),
        "qc_feedback": "",
        "qc_attempt": current_attempt,
        "qc_failed_permanently": bool(state.get("qc_failed_permanently")),
        "qc_extraction": state.get("qc_extraction"),
    }
