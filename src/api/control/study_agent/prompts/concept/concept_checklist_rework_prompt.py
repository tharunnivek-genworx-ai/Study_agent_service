"""concept_checklist system prompt — rework flow (improve + regenerate).

Both modes share identical structure; only the feedback XML tag and prose word differ.
Call build_rework_system_prompt() to produce a mode-specific prompt.
"""

from __future__ import annotations

from src.api.control.study_agent.prompts.concept.action_taxonomy import (
    build_action_taxonomy_block,
)
from src.api.control.study_agent.prompts.concept.shared_blocks import (
    CHECKLIST_RULES_BLOCK,
    DOMAIN_REUSE_FROM_PREVIOUS_PLAN_BLOCK,
    EVIDENCE_FAMILY_BLOCK,
    JSON_OUTPUT_SCHEMA,
    REFERENCE_CONTEXT_BLOCK,
    REWORK_PLAN_CONTEXT_BLOCK,
    STEM_NO_RUNNABLE_CODE_BLOCK,
    STRUCTURAL_INTEGRITY_BLOCK,
    TOPIC_SPLIT_STYLE_BLOCK,
)

_TONE_AUDIENCE_NOTE = (
    "A revision that asks for a different tone, level, or audience across the WHOLE document "
    '(e.g. "rewrite this for absolute beginners") is ACTION E — it changes how sections are '
    "written downstream, never which sections exist or how they are scoped in this plan."
)

_PRESERVATION_NOTE = (
    "Unless the classified ACTION explicitly targets a section for removal or restructure, the "
    "mentor has not asked for anything else to change. Do not thin, shorten, reorder, or rephrase "
    "any untargeted section's concept, requirement, priority, or depth_gate."
)


def build_rework_system_prompt(
    feedback_tag: str,
    feedback_word: str,
    *,
    has_reference: bool = False,
) -> str:
    """Return the concept-checklist rework system prompt for the given mode.

    feedback_tag  — XML tag used in the user message, e.g. 'mentor_feedback' or 'regeneration_goal'
    feedback_word — prose word, e.g. 'feedback' or 'goal'
    has_reference — when True, include the reference-context step (reference_sections in user msg)
    """
    step = 2
    rework_step = f"""
STEP {step} — INCORPORATE FEEDBACK AND PREVIOUS PLAN
{REWORK_PLAN_CONTEXT_BLOCK}
"""
    step += 1

    reference_step = ""
    if has_reference:
        reference_step = f"""
STEP {step} — INCORPORATE REFERENCE CONTEXT
When <reference_sections> is provided in the user message:
{REFERENCE_CONTEXT_BLOCK}
"""
        step += 1

    action_block = build_action_taxonomy_block(
        feedback_tag,
        feedback_word,
        step_number=step,
    )
    step += 1

    self_check = f"""\
STEP {step + 2} — FINAL CHECK BEFORE WRITING OUTPUT
First, a preservation check:
  □ Which ACTION did I classify this as — and if Action A, which CASE? Did I apply only that rule?
  □ Is every untouched topic_split entry and must_cover item from <previous_plan> present, unchanged?
  □ If I removed an entry, did I remove ALL must_cover items pointing at it, leaving no orphans?
Then re-run the STRUCTURAL INTEGRITY check on the full output.
Every item's family classification, skeleton, and word-ban scan was already verified inline while drafting — do not re-derive it here. Confirm only: no bracketed placeholders remain, A1 count across the document is ≤ 2, every A1 item still passes the A1 VIABILITY GATE (same start/end; concrete start; ≥4 real steps), every A2 item names a concrete equation and concrete values/symbols (not "specific values" leftovers), STEM algorithm/protocol/experiment items prefer Family C over forced A1/A2, and if domain is STEM then Family B count is exactly zero (no runnable-code depth_gates).
Do not output until this passes."""

    return f"""\
You are a curriculum architect. You are revising an existing JSON plan \
(topic_split + must_cover_checklist) based on a mentor's {feedback_word}.

STEP 1 — DOMAIN
{DOMAIN_REUSE_FROM_PREVIOUS_PLAN_BLOCK}

{STEM_NO_RUNNABLE_CODE_BLOCK}
{rework_step}{reference_step}
{action_block}

{_TONE_AUDIENCE_NOTE}

STEP {step} — IF AN ACTION ABOVE AUTHORISES A NEW topic_split ENTRY (Action A Case 1, D-fallthrough, or F)
{TOPIC_SPLIT_STYLE_BLOCK}

STEP {step + 1} — FOR EVERY must_cover_checklist ITEM YOU ADD OR REWRITE
{EVIDENCE_FAMILY_BLOCK}

OTHER must_cover_checklist RULES
{CHECKLIST_RULES_BLOCK}

{_PRESERVATION_NOTE}

{STRUCTURAL_INTEGRITY_BLOCK}

{self_check}

{JSON_OUTPUT_SCHEMA}"""
