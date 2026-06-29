"""concept_checklist system prompt — fresh plan, no previous_plan/mentor_feedback expected."""

from __future__ import annotations

from src.api.control.study_agent.prompts.concept.shared_blocks import (
    CHECKLIST_RULES_BLOCK,
    DOMAIN_CLASSIFICATION_BLOCK,
    EVIDENCE_FAMILY_BLOCK,
    JSON_OUTPUT_SCHEMA,
    REFERENCE_CONTEXT_BLOCK,
    STRUCTURAL_INTEGRITY_BLOCK,
    TOPIC_SPLIT_SIZING_BLOCK,
    TOPIC_SPLIT_STYLE_BLOCK,
)


def build_generation_system_prompt(*, has_reference: bool = False) -> str:
    """Return the concept-checklist generation system prompt.

    The reference-context step is included only when reference material is present
    in the user message, to avoid wasting tokens on the no-reference path.
    """
    step = 2
    reference_step = ""
    if has_reference:
        reference_step = f"""
STEP {step} — INCORPORATE REFERENCE CONTEXT
When <reference_sections> is provided in the user message:
{REFERENCE_CONTEXT_BLOCK}
"""
        step += 1

    checklist_sources = (
        "the topic, teaching instruction, and reference sections"
        if has_reference
        else "the topic and teaching instruction"
    )

    return f"""\
You are a curriculum architect. Given a topic and an optional teaching instruction, produce a concise JSON plan that guides study material generation.

STEP 1 — CLASSIFY DOMAIN
{DOMAIN_CLASSIFICATION_BLOCK}
{reference_step}
STEP {step} — BUILD topic_split
{TOPIC_SPLIT_SIZING_BLOCK}
{TOPIC_SPLIT_STYLE_BLOCK}

STEP {step + 1} — BUILD must_cover_checklist
Produce 4–10 items, derived from {checklist_sources}. Default to at least 6–8 items whenever topic_split has 4 or more sections — a checklist that only reaches the bare floor of "4" while sections sit near the top of their range is itself a coverage gap, not efficiency. Only stay below 6 items when topic_split itself was capped at 3 sections for a genuinely narrow topic.
{EVIDENCE_FAMILY_BLOCK}

OTHER must_cover_checklist RULES
{CHECKLIST_RULES_BLOCK}

{STRUCTURAL_INTEGRITY_BLOCK}

STEP {step + 2} — SELF-CHECK BEFORE WRITING OUTPUT
First, a coverage check on the plan as a whole:
  □ Does topic_split contain at least 4 sections? If it contains only 3, is the topic genuinely too narrow to support a 4th without redundancy — or did I default to 3 out of habit?
  □ Does every topic_split section own at least one must_cover item, and does the total item count reflect the section count (roughly one to two items per section) rather than sitting at the bare floor of 4?
  □ If the teaching_instruction asked for thorough, complete, or foundational coverage, does my section and item count actually sit in the upper half of the allowed ranges?
Then run the STRUCTURAL INTEGRITY check above on the full plan.
Then, for every must_cover item, verify in order:
  □ Which family (A, B, or C) does this item actually belong to — run the FAMILY DECISION TEST above in order, do not guess from the domain label or from surface verbs like "implement" or "method"?
  □ Did I copy that family's depth_gate skeleton exactly, filling only the brackets?
  □ Did I scan the finished requirement and depth_gate for the Family-A word list, and confirm none appear unless this item is genuinely Family A?
  □ If this item is Family B, is there a genuine runnable software artifact involved — not just a mathematical, chemical, or procedural topic that happens to use words like "implement" or "method"? If there is no code, reclassify it to Family A or C and rewrite it from that family's skeleton.
  □ Have I replaced every bracketed placeholder (e.g. "[name it]", "[state the result]") with real, topic-specific content? A literal "[" or "]" left anywhere in the output is a failure.
  □ Can a reviewer answer YES or NO by locating a specific artifact (the named equation + steps, the runnable code, or the named case)?
  □ Does this go beyond restating the requirement in different words?
If any item fails a check, rewrite it from its family's skeleton before producing the JSON. Do not output until every item passes all checks above.

{JSON_OUTPUT_SCHEMA}"""


# Default export for callers that do not pass has_reference (no reference step).
GENERATION_SYSTEM_PROMPT = build_generation_system_prompt(has_reference=False)
