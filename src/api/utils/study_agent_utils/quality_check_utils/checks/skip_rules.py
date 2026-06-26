"""Rules for when the QC node should be skipped."""

from __future__ import annotations

from src.api.control.study_agent.states.state import StudyMaterialGraphState


def should_skip_qc(state: StudyMaterialGraphState) -> bool:
    """Skip QC for vague responses during improve/regenerate tasks."""
    mode = state.get("generation_mode") or "generate"
    if mode == "improve" and state.get("improve_status") == "vague":
        return True
    if mode == "regenerate" and state.get("regenerate_status") == "vague":
        return True
    return False
