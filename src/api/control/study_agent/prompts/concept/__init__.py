# concept_checklist/__init__.py

from __future__ import annotations

import json
from typing import Any

from src.api.control.study_agent.prompts.concept.checklist_realign_prompt import (
    build_checklist_realign_system_prompt,
    build_checklist_realign_user_message,
    truncate_research_notes,
)
from src.api.control.study_agent.prompts.concept.concept_checklist_generation_prompt import (
    build_generation_system_prompt,
)
from src.api.control.study_agent.prompts.concept.concept_checklist_rework_prompt import (
    build_rework_system_prompt,
)

__all__ = [
    "build_checklist_realign_system_prompt",
    "build_checklist_realign_user_message",
    "build_concept_checklist_system_prompt",
    "build_concept_checklist_user_message",
    "truncate_research_notes",
]

_USER_MESSAGE_CLOSING = (
    "\nGenerate the JSON plan now. "
    "For every must_cover item, pick its evidence family (A/B/C) from what the item is actually about, "
    "copy that family's depth_gate skeleton, and fill only the brackets. "
    "If domain is STEM, Family B is forbidden — never write runnable-code / script depth_gates; use Family A or C instead. "
    "For STEM algorithms, protocols, experiments, and qualitative applications, prefer Family C; use A1 only if the A1 VIABILITY GATE passes; use A2 only when you can name a real equation and concrete values or symbols. "
    "Run the Family-A word-ban scan on every Family B and Family C item before output. "
    "Ensure each section has linked checklist items with specific requirements and fully filled-in depth_gates — "
    "not a thin or generic plan."
)


_PREVIOUS_PLAN_PREAMBLE = (
    "This is the previous concept plan from the prior run. "
    "During improvement or regeneration, use it as your primary ground truth — "
    "read it first, locate the exact topic_split sections and must_cover_checklist items here, "
    "then apply add, remove, or modify requests against those ids and headings."
)


def build_concept_checklist_system_prompt(
    generation_type: str,
    *,
    has_reference: bool = False,
) -> str:
    if generation_type == "generate":
        return build_generation_system_prompt(has_reference=has_reference)

    if generation_type == "improve":
        return build_rework_system_prompt(
            "mentor_feedback",
            "feedback",
            has_reference=has_reference,
        )

    if generation_type == "regenerate":
        return build_rework_system_prompt(
            "regeneration_goal",
            "goal",
            has_reference=has_reference,
        )

    raise ValueError(f"Unknown generation_type: {generation_type!r}")


def build_concept_checklist_user_message(
    topic_title: str,
    teaching_instruction: str = "",
    reference_sections: list[dict[str, Any]] | None = None,
    *,
    mentor_feedback: str | None = None,
    generation_mode: str = "generate",
    previous_plan: dict[str, Any] | None = None,
) -> str:
    parts: list[str] = []

    if previous_plan:
        plan_json = json.dumps(previous_plan, ensure_ascii=False)

        if generation_mode in ("improve", "regenerate"):
            parts.append(
                f"<previous_plan>\n{_PREVIOUS_PLAN_PREAMBLE}\n{plan_json}\n</previous_plan>"
            )

        else:
            parts.append(f"<previous_plan>\n{plan_json}\n</previous_plan>")

    parts.append(f"<topic>{topic_title}</topic>")

    if teaching_instruction.strip():
        parts.append(
            f"\n<teaching_instruction>\n{teaching_instruction.strip()}\n</teaching_instruction>"
        )

    if generation_mode == "regenerate" and mentor_feedback:
        parts.append(f"\n<regeneration_goal>\n{mentor_feedback}\n</regeneration_goal>")

    elif generation_mode == "improve" and mentor_feedback:
        parts.append(f"\n<mentor_feedback>\n{mentor_feedback}\n</mentor_feedback>")

    if reference_sections:
        sections_json = json.dumps(reference_sections, ensure_ascii=False)

        parts.append(f"\n<reference_sections>\n{sections_json}\n</reference_sections>")

    parts.append(_USER_MESSAGE_CLOSING)

    return "\n".join(parts)
