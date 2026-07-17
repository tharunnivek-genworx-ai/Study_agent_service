# src/api/control/study_agent/prompts/section/section_block_relocate_prompt.py
"""Minimal section patch prompts for placement-only QC failures.

Used when deterministic relocation left low-confidence spans and
``qc_relocation_plans`` is populated. Unlike ``section_rework_prompt``, this
branch excludes substance rework rules and scoped must_cover checklists —
the LLM should only move block content, not rewrite teaching material.

Output: ``{"sections": [...]}`` — field-level merge preserves untouched prose.
"""

from __future__ import annotations

import json

from src.api.control.study_agent.prompts.generation.external import (
    resolve_external_addendum,
)
from src.api.control.study_agent.prompts.generation.generation_prompt import (
    format_reference_user_block,
)
from src.api.control.study_agent.prompts.generation.output_schemas import (
    build_section_patch_output_schema,
)
from src.api.control.study_agent.prompts.section.section_rework_prompt import (
    _subsection_remediation_targets,
    build_sections_to_fix_block,
    build_subsection_remediation_block,
)

_BASE_SYSTEM_INTRO = """\
You are fixing block-placement formatting in specific study document sections.
Mandate: relocate content between prose (content), formula_blocks, and code_blocks ONLY.
Do not add coverage, rewrite teaching substance, or paraphrase prose beyond minimal edits required for relocation.
Rewrite ONLY the sections listed in <sections_to_fix>. Do not add, remove, or rename sections.
"""
_RELOCATION_RULES_BLOCK = """\
RELOCATION RULES
- Apply each high-confidence action implied by <relocation_plan> and the listed failures.
- Inline equations, LaTeX, or display-math in content → move to formula_blocks on the same section or named subsection.
- Math in code_blocks → move to formula_blocks; executable code in formula_blocks → move to code_blocks.
- Empty block explanation fields → fill with a brief 1-2 sentence explanation of what the block shows.
- When dereferencing notation already defined in formula_blocks, replace the inline span with plain prose (e.g. "the derivative") — do not duplicate the equation in content.
- Do not change facts, examples, headings, subsection structure, or teaching depth.
"""
_FINAL_CHECK_BLOCK = """\
FINAL CHECK before outputting (do not print):
1. Output contains only sections from <sections_to_fix> with preserved ids.
2. Every listed placement failure is addressed by moving blocks — not by rewriting substance.
3. Every code_block and formula_block has a non-empty "explanation" field.
4. No section or subsection "content" field contains inline equations, derivative shorthand (e.g. f'(x)=), or LaTeX commands.
5. JSON is valid.\
"""
_REFERENCE_ADDENDUM = """
Reference material is provided. Use it only to preserve factual accuracy when relocating blocks. Do not invent facts not in the reference.\
"""
_NO_REFERENCE_ADDENDUM = """
No reference material is provided. Preserve the factual content of each section while relocating blocks only.\
"""


def _build_base_system(domain: str | None) -> str:
    return (
        _BASE_SYSTEM_INTRO
        + build_section_patch_output_schema(domain)
        + "\n"
        + _RELOCATION_RULES_BLOCK
        + _FINAL_CHECK_BLOCK
    )


def _select_reference_addendum(
    *,
    has_reference: bool,
    reference_kind: str = "none",
    domain: str | None = None,
) -> str:
    if reference_kind == "external":
        return resolve_external_addendum(domain)
    if reference_kind == "pdf" or has_reference:
        return _REFERENCE_ADDENDUM
    return _NO_REFERENCE_ADDENDUM


def build_system_prompt(
    *,
    has_reference: bool,
    domain: str | None = None,
    reference_kind: str = "none",
) -> str:
    return _build_base_system(domain) + _select_reference_addendum(
        has_reference=has_reference,
        reference_kind=reference_kind,
        domain=domain,
    )


def build_relocation_plan_block(plans: list[dict]) -> str:
    if not plans:
        return ""
    payload = json.dumps({"relocation_plans": plans}, indent=2, ensure_ascii=False)
    return f"\n<relocation_plan>\n{payload}\n</relocation_plan>"


def build_user_message(
    topic_title: str,
    teaching_instruction: str,
    document_outline: str,
    section_failures: list[dict],
    *,
    document: dict,
    relocation_plans: list[dict],
    domain: str = "",
    topic_split_block: str = "",
    reference_block: str = "",
) -> str:
    parts = [
        f"<topic>{topic_title}</topic>",
        f"\n<teaching_instruction>\n{teaching_instruction}\n</teaching_instruction>",
        f"\n<document_outline>\n{document_outline.strip()}\n</document_outline>",
        build_sections_to_fix_block(section_failures, document=document),
        build_relocation_plan_block(relocation_plans),
    ]
    if domain:
        parts.append(f"\n<domain>{domain}</domain>")
    if topic_split_block:
        parts.append(topic_split_block)
    if reference_block:
        parts.append(reference_block)
    subsection_targets = _subsection_remediation_targets(section_failures)
    subsection_block = build_subsection_remediation_block(subsection_targets)
    if subsection_block:
        parts.append(subsection_block)
    parts.append(
        "\nRewrite ONLY the sections in <sections_to_fix>. "
        "Change only block fields (content, formula_blocks, code_blocks, and subsection block fields); "
        "do not paraphrase prose or alter teaching substance. "
        'Return JSON with {"sections": [...]} containing only the patched sections.'
    )
    return "\n".join(parts)


def format_reference_block(
    extracted_reference_text: str,
    *,
    has_reference: bool,
    reference_kind: str = "none",
) -> str:
    return format_reference_user_block(
        extracted_reference_text,
        has_reference=has_reference,
        reference_kind=reference_kind,
    )
