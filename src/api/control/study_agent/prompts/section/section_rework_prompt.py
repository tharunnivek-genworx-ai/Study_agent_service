# src/api/control/study_agent/prompts/section_rework_prompt.py
"""Section rework prompts — rewrite only the sections that failed QC."""

from __future__ import annotations

import json
import re

from src.api.control.study_agent.prompts.generation.generation_prompt import (
    format_reference_user_block,
)
from src.api.utils.prompt_utils.domain_merge import merge_domain_blocks
from src.api.utils.study_agent_utils.generation.must_cover_checklist_format import (
    checklist_section_id,
    format_must_cover_checklist_line,
)

SECTION_OUTPUT_SCHEMA = """\
Return ONLY valid JSON — no markdown fences, no prose outside the JSON:
{
  "sections": [
    {
      "id": "<same id as the failed section — required, do not change>",
      "heading": "<title>",
      "content": "<prose — no fenced code blocks, no markdown headings, no equations inside this field>",
      "code_blocks": [{"language": "<lang>", "code": "<code>", "explanation": "<2-3 sentences: what it demonstrates, which concept, one thing to notice>"}],
      "formula_blocks": [{"notation": "<e.g. LaTeX or plain-text>", "formula": "<the equation, reaction, or derivation step>", "explanation": "<2-3 sentences: what it represents, every variable defined, one thing to notice>"}],
      "subsections": [{
        "heading": "<title>",
        "content": "<prose only — no fenced code blocks, no markdown headings, no equations inside this field>",
        "code_blocks": [{"language": "<lang>", "code": "<code>", "explanation": "<2-3 sentences>"}],
        "formula_blocks": [{"notation": "<e.g. LaTeX>", "formula": "<equation or derivation step>", "explanation": "<2-3 sentences>"}]
      }]
    }
  ]
}
Omit "code_blocks", "formula_blocks", and "subsections" entirely when empty. Omit subsection "code_blocks" and "formula_blocks" when empty.
Preserve each section's "id" exactly. The "explanation" field inside every code_block and formula_block is mandatory.
Equations and derivations belong in formula_blocks at section or subsection level — never inline in "content".\
"""
_SUBSECTION_EVIDENCE_PATTERN = re.compile(
    r"subsection\s+['\"]([^'\"]+)['\"]",
    re.IGNORECASE,
)
STEM_ACCURACY_BLOCK = """- STEM: equations and reactions belong in formula_blocks and must be correct and dimensionally consistent; worked examples must trace step-by-step to the correct answer; constants must carry correct values and units. Never state a reaction or formula you cannot verify as real. For chemistry: verify the reactants, mechanism, and products are correct for the described reaction type — a correctly formatted but mechanistically wrong reaction is a factual error.
- STEM DERIVATION RULE: When the section's linked checklist item demands derivation, proof, or step-by-step calculation, write sequential algebraic or logical steps in formula_blocks — one step per entry, each following from the previous. Do NOT provide Python, sympy, scipy, numpy, or any other computational library code as the derivation. The retry QC will fail the section again if code substitutes for formula_block steps."""
PROGRAMMING_ACCURACY_BLOCK = '- Programming: code must be syntactically valid and run correctly on the demonstrated path; no undefined symbols; verify every API call is real for the stated language/version; every code_block must have a non-empty "explanation" field.'
CONCEPTUAL_ACCURACY_BLOCK = "- Conceptual: named facts must be accurate; do not introduce code_blocks or formula_blocks; do not invent statistics attributed to named organisations."
_ACCURACY_RULES_HEADER = """\
ACCURACY RULES
- Every claim must be true for the specific language, framework, or field in the topic."""
_BASE_SYSTEM_PREFIX = f"""\
You are an expert educator rewriting specific failed sections of a study document.
Mandate: rewrite ONLY the sections listed in <sections_to_fix>. Do not add, remove, or rename sections.
{SECTION_OUTPUT_SCHEMA}
FAILURE REMEDIATION
- Address every listed failure at its root cause. Fixing phrasing while leaving the underlying error is NOT a fix.
- Thin coverage: add new concepts, worked examples, or subsections — do not just expand existing sentences.
- Incorrect code: fix the logical error, not just the explanation text.
- Undefined symbol: add the definition or import within the same block.
- Duplicate method name silently replacing the first: either remove the duplicate, or explicitly explain that the second replaces the first and show the intended corrected pattern.
- Empty explanation field: write a proper 2-3 sentence explanation for every code_block or formula_block.
- Code, pseudo-code, or a fake "language" used to render an equation or reaction: move that content into a formula_block (for STEM) or remove it entirely and explain the concept in prose (for Conceptual) — do not leave it as a code_block.
- Python/scipy/sympy used as a derivation where sequential algebraic steps were required: remove the code block and replace with formula_blocks showing each algebraic step explicitly. Code shows computation; it does not demonstrate the reasoning chain and will fail retry QC again.
- Equation in section or subsection content (document_coherence / det_equation_in_content): when evidence names subsection '<heading>', rewrite THAT subsection's "content" to prose-only — no f'(x)=, no \\frac, no \\lim, no LaTeX, no display-math. Move every equation into "formula_blocks" on that same subsection (preferred) or at section level. Adding section-level formula_blocks while leaving equations in the named subsection's content is NOT a fix and will fail retry QC again.
"""
_SUBSTANCE_RULES_BLOCK = """\
SUBSTANCE RULES
- Each rewritten section must deliver: definition + mechanism + concrete example, at genuine teaching depth rather than a brief summary.
- Naming a concept in a heading or one sentence is not coverage.
- When a section has a linked checklist item, satisfy its depth_gate — demonstrated, not merely mentioned.
- When failures reference thin coverage or a `must_cover` gap, add subsections or `formula_blocks` until every `depth_gate` component in `<scoped_must_cover_checklist>` is demonstrably satisfied.
- Examples must be meaningfully distinct; renamed variables are not a new example.
"""
_FINAL_CHECK_BLOCK = """\
FINAL CHECK before outputting (do not print):
1. Output contains only sections from <sections_to_fix> with preserved ids.
2. Every listed failure is addressed at its root cause.
3. No code references undefined symbols or non-existent APIs.
4. Every code_block and formula_block has a non-empty "explanation" field.
5. STEM sections requiring derivation contain sequential algebraic steps in formula_blocks — not Python code and not a formula statement with a one-sentence explanation.
6. code_blocks and formula_blocks are used only where the section's domain genuinely calls for them.
7. No section or subsection "content" field contains inline equations, derivative shorthand (e.g. f'(x)=), or LaTeX commands — those belong in formula_blocks.
8. JSON is valid.\
"""
_REFERENCE_ADDENDUM = """
Reference material is provided. Treat it as authoritative when fixing sections. Do not invent facts not in the reference.\
"""
_NO_REFERENCE_ADDENDUM = """
No reference material is provided. Write from authoritative knowledge of the topic.\
"""


def build_accuracy_rules_block(domain: str | None) -> str:
    domain_bullets = merge_domain_blocks(
        {
            "STEM": STEM_ACCURACY_BLOCK,
            "Programming": PROGRAMMING_ACCURACY_BLOCK,
            "Conceptual": CONCEPTUAL_ACCURACY_BLOCK,
        },
        domain,
        separator="\n",
    )
    return _ACCURACY_RULES_HEADER + "\n" + domain_bullets


def _build_base_system(domain: str | None) -> str:
    return (
        _BASE_SYSTEM_PREFIX
        + build_accuracy_rules_block(domain)
        + "\n\n"
        + _SUBSTANCE_RULES_BLOCK
        + _FINAL_CHECK_BLOCK
    )


_BASE_SYSTEM = _build_base_system("")


def build_system_prompt(*, has_reference: bool, domain: str | None = None) -> str:
    return _build_base_system(domain) + (
        _REFERENCE_ADDENDUM if has_reference else _NO_REFERENCE_ADDENDUM
    )


def _subsection_headings_from_evidence(evidence: str) -> list[str]:
    return [
        match.group(1).strip()
        for match in _SUBSECTION_EVIDENCE_PATTERN.finditer(str(evidence or ""))
        if match.group(1).strip()
    ]


def _subsection_remediation_targets(
    section_failures: list[dict],
) -> dict[str, list[str]]:
    """Map section_id -> subsection headings named in failure evidence."""
    targets: dict[str, list[str]] = {}
    for bundle in section_failures:
        if not isinstance(bundle, dict):
            continue
        section_id = str(bundle.get("section_id", "")).strip()
        if not section_id:
            continue
        headings: list[str] = []
        for failure in bundle.get("failures") or []:
            if not isinstance(failure, dict):
                continue
            headings.extend(
                _subsection_headings_from_evidence(failure.get("evidence", ""))
            )
        if headings:
            deduped = list(dict.fromkeys(headings))
            targets[section_id] = deduped
    return targets


def build_subsection_remediation_block(subsection_targets: dict[str, list[str]]) -> str:
    if not subsection_targets:
        return ""
    lines = [
        "Rewrite each named subsection so its content is prose-only and every equation lives in formula_blocks:",
    ]
    for section_id, headings in sorted(subsection_targets.items()):
        for heading in headings:
            lines.append(
                f"  - section {section_id!r}, subsection {heading!r}: strip all inline math "
                f"from content; add formula_blocks on that subsection for each equation."
            )
    return (
        "\n<subsection_equation_remediation>\n"
        + "\n".join(lines)
        + "\n</subsection_equation_remediation>"
    )


def build_sections_to_fix_block(
    section_failures: list[dict],
    *,
    document: dict,
) -> str:
    from src.api.utils.study_agent_utils.quality_check_utils.document.document_merge import (
        extract_sections_by_ids,
    )

    section_ids = [
        str(item.get("section_id", "")).strip()
        for item in section_failures
        if str(item.get("section_id", "")).strip()
    ]
    sections_by_id = {
        str(s.get("id", "")).strip(): s
        for s in extract_sections_by_ids(document, section_ids)
    }
    subsection_targets = _subsection_remediation_targets(section_failures)
    entries: list[dict] = []
    for bundle in section_failures:
        section_id = str(bundle.get("section_id", "")).strip()
        if not section_id:
            continue
        current = sections_by_id.get(section_id, {})
        failures = bundle.get("failures") or []
        entry: dict = {
            "id": section_id,
            "heading": current.get("heading", bundle.get("heading", "")),
            "current_section_json": current,
            "failures": [
                {
                    "category": f.get("category", ""),
                    "evidence": f.get("evidence", ""),
                    "corrective_hint": f.get("corrective_hint", ""),
                }
                for f in failures
                if isinstance(f, dict)
            ],
        }
        if subsection_headings := subsection_targets.get(section_id):
            entry["subsections_to_fix"] = [
                {
                    "heading": heading,
                    "requirement": (
                        "Rewrite this subsection's content to prose-only with no inline "
                        "equations; move every equation into formula_blocks on this subsection."
                    ),
                }
                for heading in subsection_headings
            ]
        entries.append(entry)
    payload = json.dumps({"sections_to_fix": entries}, indent=2, ensure_ascii=False)
    return f"\n<sections_to_fix>\n{payload}\n</sections_to_fix>"


def build_scoped_checklist_block(
    checklist: list[dict],
    section_ids: list[str],
) -> str:
    target_ids = {
        str(section_id).strip() for section_id in section_ids if str(section_id).strip()
    }
    if not target_ids or not checklist:
        return ""
    scoped_items = [
        item for item in checklist if checklist_section_id(item) in target_ids
    ]
    if not scoped_items:
        return ""
    lines = "\n".join(format_must_cover_checklist_line(item) for item in scoped_items)
    return f"\n<scoped_must_cover_checklist>\n{lines}\n</scoped_must_cover_checklist>"


def build_user_message(
    topic_title: str,
    teaching_instruction: str,
    document_outline: str,
    section_failures: list[dict],
    *,
    document: dict,
    domain: str = "",
    topic_split_block: str = "",
    reference_block: str = "",
    must_cover_checklist: list[dict] | None = None,
    patch_section_ids: list[str] | None = None,
) -> str:
    scoped_checklist_block = ""
    if must_cover_checklist and patch_section_ids:
        scoped_checklist_block = build_scoped_checklist_block(
            must_cover_checklist,
            patch_section_ids,
        )
    parts = [
        f"<topic>{topic_title}</topic>",
        f"\n<teaching_instruction>\n{teaching_instruction}\n</teaching_instruction>",
        f"\n<document_outline>\n{document_outline.strip()}\n</document_outline>",
        build_sections_to_fix_block(section_failures, document=document),
    ]
    if scoped_checklist_block:
        parts.append(scoped_checklist_block)
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
    closing = (
        "\nRewrite ONLY the sections in <sections_to_fix>. "
        "Fix every listed failure at its root cause — not just its surface phrasing. "
        "Every code_block and formula_block must have a non-empty 'explanation' field. "
        'Return JSON with {"sections": [...]} containing only the rewritten sections.'
    )
    if subsection_targets:
        closing += (
            " When <subsection_equation_remediation> or subsections_to_fix is present, "
            "you MUST rewrite each named subsection: content becomes prose-only and every "
            "equation moves to formula_blocks on that subsection. Section-level formula_blocks "
            "do not excuse inline math left in subsection content."
        )
    if scoped_checklist_block:
        closing += (
            " Satisfy every depth_gate component for scoped checklist items in the rewritten section. "
            "For depth_gates requiring derivation: provide sequential algebraic steps in formula_blocks — Python code is not a derivation and will fail retry QC."
        )
    parts.append(closing)
    return "\n".join(parts)


def format_reference_block(
    extracted_reference_text: str, *, has_reference: bool
) -> str:
    return format_reference_user_block(
        extracted_reference_text, has_reference=has_reference
    )
