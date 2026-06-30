# src/api/control/study_agent/prompts/section_insert_prompt.py
"""Section insert prompts — write only the missing checklist sections."""

from __future__ import annotations

from src.api.control.study_agent.prompts.generation.generation_prompt import (
    format_reference_user_block,
)
from src.api.control.study_agent.prompts.generation.output_schemas import (
    build_json_output_schema,
)
from src.api.utils.prompt_utils.domain_merge import merge_domain_blocks
from src.api.utils.study_agent_utils.generation.must_cover_checklist_format import (
    format_must_cover_checklist_line,
)

STEM_SUBSTANCE_BLOCK = "- STEM: state equations and reactions in formula_blocks only (the STEM schema has no code_blocks), trace worked examples step-by-step to correct answers, define all variables with units. When the depth_gate demands derivation, proof, or step-by-step calculation, provide sequential algebraic or logical steps in formula_blocks — one step per formula_block entry if needed. Do NOT use Python, sympy, scipy, numpy, or any computational library as a substitute."
PROGRAMMING_SUBSTANCE_BLOCK = '- Programming: show complete runnable examples in code_blocks; every code_block must have a non-empty "explanation" field.'
CONCEPTUAL_SUBSTANCE_BLOCK = """- Conceptual: every new section must define the concept precisely (distinguishing it from adjacent or commonly confused concepts), explain the mechanism (what causes it, how it operates step by step, who the actors are, what conditions are required, and what the observable outcome is), and illustrate with at least one specific named case — name the organisation, event, legislation, or individual, describe the context, and state the outcome. When a depth_gate requires comparison: name both options and provide a real named case for each side. When a depth_gate requires causal analysis: trace precondition → trigger → mechanism → outcome; 'X caused Y' without the mechanism chain is insufficient. Never use sector-level generalisations ('many companies', 'government agencies') where a named entity is required. Do not add code_blocks or formula_blocks — all content must appear as specific named real-world scenarios in prose. Do not attribute statistics or performance metrics to named organisations unless publicly documented and widely known."""
_SUBSTANCE_RULES_COMMON = """\
SUBSTANCE RULES
- Each new section must satisfy its depth_gate — this is the minimum, not the ceiling.
- Deliver: definition + mechanism (how and why) + at least one concrete example per major concept, with the depth of a real teaching section rather than a brief summary."""
_BASE_SYSTEM_INTRO = """\
You are an expert educator writing missing sections for a study document.
Mandate: write ONLY the sections listed in <missing_checklist_items>. Do not return any existing section.
"""
_ACCURACY_RULES_BLOCK = """\
ACCURACY RULES
- Every claim must be true for the specific language, framework, or field in the topic.
- Never attribute a property to a language or field it does not belong to.
- Never invent named facts, API names, method signatures, reactions, or constants.
- Never attribute statistics, percentages, or performance metrics to named organisations unless those figures are publicly documented.
- Code must be syntactically valid. Every symbol must be defined or imported in the same block.
- Never define the same method or function name twice in the same scope without explaining the consequence.
- Verify every API call is real for the stated language/version.
"""
_FINAL_CHECK_BLOCK = """\
FINAL CHECK before outputting (do not print):
1. Output contains only sections for <missing_checklist_items> with correct ids.
2. Every depth_gate requirement is substantively satisfied with evidence.
3. For STEM depth_gates requiring derivation: sequential algebraic steps appear in formula_blocks, not in Python code or formula statements alone.
4. No code uses undefined symbols or non-existent APIs.
5. code_blocks and formula_blocks are used only where the section's domain genuinely calls for them.
6. No invented statistics attributed to named organisations.
7. JSON is valid.\
"""
_REFERENCE_ADDENDUM = """
Reference material is provided. Treat it as authoritative when writing new sections. Do not invent facts not in the reference.\
"""
_NO_REFERENCE_ADDENDUM = """
No reference material is provided. Write from authoritative knowledge of the topic.\
"""


def build_substance_rules_block(domain: str | None) -> str:
    domain_bullets = merge_domain_blocks(
        {
            "STEM": STEM_SUBSTANCE_BLOCK,
            "Programming": PROGRAMMING_SUBSTANCE_BLOCK,
            "Conceptual": CONCEPTUAL_SUBSTANCE_BLOCK,
        },
        domain,
        separator="\n",
    )
    return (
        _SUBSTANCE_RULES_COMMON
        + "\n"
        + domain_bullets
        + "\n"
        + "- Examples must be meaningfully distinct from each other."
    )


def _build_base_system(domain: str | None) -> str:
    schema = build_json_output_schema(domain).replace(
        '"id": "<topic_split id when provided; checklist id otherwise; null for unlisted sections>"',
        '"id": "<section_id from the checklist item — required>"',
    )
    return (
        _BASE_SYSTEM_INTRO
        + schema
        + "\n"
        + _ACCURACY_RULES_BLOCK
        + build_substance_rules_block(domain)
        + "\n\n"
        + _FINAL_CHECK_BLOCK
    )


_BASE_SYSTEM = _build_base_system("")


def build_system_prompt(*, has_reference: bool, domain: str | None = None) -> str:
    return _build_base_system(domain) + (
        _REFERENCE_ADDENDUM if has_reference else _NO_REFERENCE_ADDENDUM
    )


def build_missing_checklist_block(missing_checklist_items: list[dict]) -> str:
    lines = "\n".join(
        format_must_cover_checklist_line(item) for item in missing_checklist_items
    )
    return f"\n<missing_checklist_items>\n{lines}\n</missing_checklist_items>"


def build_topic_split_block(topic_split: list[dict]) -> str:
    if not topic_split:
        return ""
    lines = "\n".join(
        f"  - [{e.get('id', '')}] {e.get('heading', '')} — {e.get('purpose', '')}"
        for e in topic_split
    )
    return f"\n<topic_split>\n{lines}\n</topic_split>"


def build_user_message(
    topic_title: str,
    teaching_instruction: str,
    document_outline: str,
    missing_checklist_items: list[dict],
    *,
    topic_split: list[dict] | None = None,
    domain: str = "",
    reference_block: str = "",
) -> str:
    parts = [
        f"<topic>{topic_title}</topic>",
        f"\n<teaching_instruction>\n{teaching_instruction}\n</teaching_instruction>",
        f"\n<document_outline>\n{document_outline.strip()}\n</document_outline>",
        build_missing_checklist_block(missing_checklist_items),
    ]
    if domain:
        parts.append(f"\n<domain>{domain}</domain>")
    split_block = build_topic_split_block(topic_split or [])
    if split_block:
        parts.append(split_block)
    if reference_block:
        parts.append(reference_block)
    parts.append(
        "\nWrite ONLY the missing sections in <missing_checklist_items>. "
        "Satisfy every depth_gate component with demonstrable evidence. "
        "For STEM depth_gates requiring derivation: provide sequential algebraic steps in formula_blocks — Python code is not a derivation. "
        'Return JSON with {"sections": [...]} containing only the new sections.'
    )
    return "\n".join(parts)


def format_reference_block(
    extracted_reference_text: str, *, has_reference: bool
) -> str:
    return format_reference_user_block(
        extracted_reference_text, has_reference=has_reference
    )
