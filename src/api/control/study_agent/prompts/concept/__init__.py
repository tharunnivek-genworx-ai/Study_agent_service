# concept_checklist/__init__.py
from __future__ import annotations

import json
from typing import Any

from src.api.control.study_agent.prompts.concept.concept_checklist_generation_prompt import (
    GENERATION_SYSTEM_PROMPT,
)
from src.api.control.study_agent.prompts.concept.concept_checklist_improvement_prompt import (
    IMPROVEMENT_SYSTEM_PROMPT,
)
from src.api.control.study_agent.prompts.concept.concept_checklist_regeneration_prompt import (
    REGENERATION_SYSTEM_PROMPT,
)

_PROMPTS = {
    "generate": GENERATION_SYSTEM_PROMPT,
    "improve": IMPROVEMENT_SYSTEM_PROMPT,
    "regenerate": REGENERATION_SYSTEM_PROMPT,
}

_USER_MESSAGE_CLOSING = (
    "\nGenerate the JSON plan now. "
    "For every must_cover item, pick its evidence family (A/B/C) from what the item is actually about, "
    "copy that family's depth_gate skeleton, and fill only the brackets. "
    "Run the Family-A word-ban scan on every Family B and Family C item before output. "
    "Ensure each section has linked checklist items with specific requirements and fully filled-in depth_gates — "
    "not a thin or generic plan."
)


def build_concept_checklist_system_prompt(generation_type: str) -> str:
    try:
        return _PROMPTS[generation_type]
    except KeyError as err:
        raise ValueError(f"Unknown generation_type: {generation_type!r}") from err


def build_concept_checklist_user_message(
    topic_title: str,
    teaching_instruction: str = "",
    reference_sections: list[dict[str, Any]] | None = None,
    *,
    mentor_feedback: str | None = None,
    generation_mode: str = "generate",
    previous_plan: dict[str, Any] | None = None,
) -> str:
    parts = [f"<topic>{topic_title}</topic>"]
    if teaching_instruction.strip():
        parts.append(
            f"\n<teaching_instruction>\n{teaching_instruction.strip()}\n</teaching_instruction>"
        )
    if generation_mode == "regenerate" and mentor_feedback:
        parts.append(f"\n<regeneration_goal>\n{mentor_feedback}\n</regeneration_goal>")
    elif generation_mode == "improve" and mentor_feedback:
        parts.append(f"\n<mentor_feedback>\n{mentor_feedback}\n</mentor_feedback>")
    if previous_plan:
        plan_json = json.dumps(previous_plan, ensure_ascii=False)
        parts.append(f"\n<previous_plan>\n{plan_json}\n</previous_plan>")
    if reference_sections:
        sections_json = json.dumps(reference_sections, ensure_ascii=False)
        parts.append(f"\n<reference_sections>\n{sections_json}\n</reference_sections>")
    parts.append(_USER_MESSAGE_CLOSING)
    return "\n".join(parts)
