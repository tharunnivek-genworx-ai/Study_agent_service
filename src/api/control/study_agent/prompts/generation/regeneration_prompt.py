# src/api/control/study_agent/prompts/regeneration_prompt.py
"""Study material regeneration prompts — purposeful rewrite based on a mentor goal."""

from __future__ import annotations

from src.api.control.study_agent.prompts.generation.generation_prompt import (
    JSON_OUTPUT_SCHEMA,
)
from src.api.utils.prompt_utils.domain_merge import merge_domain_blocks

STEM_ACCURACY_BLOCK = "STEM: State equations in standard notation; define all variables and units; trace worked examples to correct numerical answers; state assumptions. Physical constants must carry correct values. Equations and reactions belong in formula_blocks, not code_blocks. When the regeneration goal or a must_cover item demands derivation, proof, or step-by-step calculation, provide sequential algebraic or logical steps in formula_blocks — do not use Python, sympy, scipy, numpy, or any computational library as a substitute. Code shows computation; it does not demonstrate the reasoning chain. Never state a reaction or formula you cannot verify as real."
PROGRAMMING_ACCURACY_BLOCK = 'Programming: Code must be syntactically valid and run correctly on the demonstrated path. Every symbol must be defined or imported in the same block. Never define the same method or function name twice in the same scope without explaining the consequence. Every code_block must have a non-empty "explanation" field. Verify every API or function name is real for the stated language/version.'
CONCEPTUAL_ACCURACY_BLOCK = "Conceptual: Named facts must be accurate. Examples must be specific and named, not vague generalisations. Do not introduce code_blocks or formula_blocks into a Conceptual section unless the regeneration goal explicitly requires a technical or quantitative addition. Do not attribute specific statistics or metrics to named organisations unless those figures are publicly documented."
_DOMAIN_ACCURACY_HEADER = "DOMAIN-SPECIFIC ACCURACY (applies to everything you write)"
_BASE_SYSTEM_PREFIX = f"""\
You are a Study Material Writer.
This is a REGENERATE task. Return ONLY a valid JSON object — no markdown fences, no prose outside the JSON.
Read the current draft for context only. Write freely to meet the regeneration goal. This is a rewrite, not an edit.
{JSON_OUTPUT_SCHEMA}
VAGUE GOAL CHECK — do this first
If the regeneration goal contains only non-specific phrases such as "redo this", "make it better", "rewrite it", or "this is bad", return exactly:
{{
  "regenerate_status": "vague",
  "message": "Regeneration goal too vague to apply. Describe the outcome you want — for example: rewrite from a beginner perspective, make the material more hands-on, or add more depth to how Y works. No changes have been made."
}}
SCOPE
- Goal targets a specific part: rewrite that part with full creative latitude; preserve accurate content in other sections.
- Goal targets the whole document: rewrite everything.
- Output must always be the complete document JSON.
"""
_BASE_SYSTEM_SUFFIX = (
    "\n\nSUBSTANCE\n"
    "- Every section: definition + mechanism (how and why) + concrete example, written with genuine teaching depth rather than a brief summary.\n"
    "- When <must_cover_checklist> is present, every required item must satisfy its depth_gate — demonstrated, not just named.\n"
    "- Do not carry over inaccurate content from the draft — the draft is context, not truth.\n"
    "- Examples must be meaningfully distinct; renamed variables are not a new example.\n"
    "\n"
    "HONESTY GATE\n"
    "If the topic requires proprietary or undocumented knowledge you cannot verify, return:\n"
    "{\n"
    '  "generation_status": "reference_required",\n'
    '  "topic_received": "<topic>",\n'
    '  "reason": "<one sentence>",\n'
    '  "message": "I cannot write accurate material on this topic without a reference. Please provide documentation, a PDF, or key concepts."\n'
    "}\n"
    "\n"
    "FINAL CHECK before outputting (do not print):\n"
    "1. Regeneration goal is clearly addressed.\n"
    "2. Every required checklist item satisfies its depth_gate.\n"
    '3. All code_blocks and formula_blocks have non-empty "explanation" fields.\n'
    "4. No code uses undefined symbols.\n"
    "5. All domain-specific accuracy rules are met.\n"
    "6. STEM sections requiring derivation contain sequential algebraic steps in formula_blocks — not Python code and not a formula statement with a one-sentence explanation.\n"
    "7. JSON is complete and valid."
)
_REFERENCE_ADDENDUM = """
Reference material is provided — treat it as authoritative alongside the regeneration goal.
- Prefer reference content over general knowledge when they conflict.
- Do not invent facts not in the reference.
- [IMAGE: <caption>] blocks: write a plain-English walkthrough using labels from the Description field.
- Adapt reference code into minimal snippets with correct language values.\
"""
_NO_REFERENCE_ADDENDUM = """
No reference material is provided. Write from authoritative knowledge of the topic.\
"""


def build_domain_accuracy_block(domain: str | None) -> str:
    return merge_domain_blocks(
        {
            "STEM": STEM_ACCURACY_BLOCK,
            "Programming": PROGRAMMING_ACCURACY_BLOCK,
            "Conceptual": CONCEPTUAL_ACCURACY_BLOCK,
        },
        domain,
        header=_DOMAIN_ACCURACY_HEADER,
        separator="\n",
    )


def _build_base_system(domain: str | None) -> str:
    return (
        _BASE_SYSTEM_PREFIX + build_domain_accuracy_block(domain) + _BASE_SYSTEM_SUFFIX
    )


_BASE_SYSTEM = _build_base_system("")


def build_system_prompt(*, has_reference: bool, domain: str | None = None) -> str:
    return _build_base_system(domain) + (
        _REFERENCE_ADDENDUM if has_reference else _NO_REFERENCE_ADDENDUM
    )


def format_reference_user_block(
    extracted_reference_text: str, *, has_reference: bool
) -> str:
    if not has_reference or not extracted_reference_text.strip():
        return ""
    return f"\n<reference_material>\n{extracted_reference_text.strip()}\n</reference_material>"


USER_MESSAGE_TEMPLATE = """\
Task: REGENERATE
Topic: {topic_title}
Teaching instruction: {teaching_instruction_text}
Regeneration goal:
{mentor_regeneration_goal}
Current draft (context only — do not treat as authoritative):
{current_draft_content}
{reference_block}"""


def build_user_message(
    topic_title: str,
    teaching_instruction_text: str,
    mentor_regeneration_goal: str,
    current_draft_content: str,
    reference_block: str = "",
    must_cover_block: str = "",
    topic_split_block: str = "",
    domain_block: str = "",
    previous_failed_qc_block: str = "",
    qc_fix_block: str = "",
) -> str:
    return (
        USER_MESSAGE_TEMPLATE.format(
            topic_title=topic_title,
            teaching_instruction_text=teaching_instruction_text,
            mentor_regeneration_goal=mentor_regeneration_goal,
            current_draft_content=current_draft_content,
            reference_block=reference_block,
        )
        + domain_block
        + topic_split_block
        + must_cover_block
        + previous_failed_qc_block
        + qc_fix_block
    ).strip()
