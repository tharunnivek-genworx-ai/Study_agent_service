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

    return f"""\
You are a curriculum architect. You are revising an existing JSON plan \
(topic_split + must_cover_checklist) based on a mentor's {feedback_word}.

STEP 1 — DOMAIN
{DOMAIN_REUSE_FROM_PREVIOUS_PLAN_BLOCK}
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

STEP {step + 2} — SELF-CHECK BEFORE WRITING OUTPUT
First, a preservation check:
  □ Which ACTION (A–F) did I classify this {feedback_word} as, and — if Action A — which CASE (1 or 2)? Did I apply only that action/case's rule?
  □ For every topic_split entry and must_cover_checklist item that existed in <previous_plan> and that my classified action did not target, is it present in my output with identical id, heading/concept, requirement, priority, section_id, and depth_gate — unchanged and not thinned?
  □ If I added a new topic_split entry (Action A Case 1), is its id genuinely unused in <previous_plan>?
  □ If I added a subtopic (Action A Case 2), does the new must_cover item's section_id point to an EXISTING ts_N — not a new id?
  □ If I removed an entry, did I remove ALL must_cover_checklist items that pointed at it, leaving no orphans?
Then run the STRUCTURAL INTEGRITY check above on the full output (not just the new items).
Then, for every NEW or REWRITTEN must_cover item only, verify in order:
  □ Which family (A, B, or C) does this item actually belong to — run the FAMILY DECISION TEST above in order, do not guess from the domain label or from surface verbs like "implement" or "method"?
  □ Did I copy that family's depth_gate skeleton exactly, filling only the brackets?
  □ Did I scan for the Family-A word list and confirm none appear unless this item is genuinely Family A?
  □ If this item is Family B, is there a genuine runnable software artifact involved — not just a mathematical, chemical, or procedural topic that happens to use words like "implement" or "method"? If there is no code, reclassify it to Family A or C and rewrite it from that family's skeleton.
  □ Have I replaced every bracketed placeholder (e.g. "[name it]", "[state the result]") with real, topic-specific content? A literal "[" or "]" left anywhere in the output is a failure.
  □ Can a reviewer answer YES or NO by locating a specific artifact?
If any check fails, fix it before producing the JSON. Do not output until every check above passes.

{JSON_OUTPUT_SCHEMA}"""


IMPROVE_SYSTEM_PROMPT = build_rework_system_prompt("mentor_feedback", "feedback")
REGENERATE_SYSTEM_PROMPT = build_rework_system_prompt("regeneration_goal", "goal")
