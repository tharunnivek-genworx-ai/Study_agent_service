# src/api/control/study_agent/prompts/section/section_rework_prompt.py
"""Section rework prompts for QC ``section_patch`` retries.

Unlike full regen (``generation_prompt`` + flat ``qc_feedback``), patch retries use
structured ``qc_section_failures`` embedded as ``<sections_to_fix>`` JSON with:
  - ``current_section_json`` (from ``extract_sections_by_ids``)
  - ``failures``: category, evidence, corrective_hint per check
  - optional ``subsections_to_fix`` when deterministic evidence names a subsection

There is no separate deterministic-only prompt branch; all failure types share
this prompt. Subsection targeting uses regex on evidence text
(``subsection 'Heading'``) from ``det_equation_in_content`` etc.

Output: ``{"sections": [...]}`` — whole section dicts merged by id (not line-level).
"""

from __future__ import annotations

import json

from src.api.control.study_agent.prompts.generation.generation_prompt import (
    format_reference_user_block,
)
from src.api.control.study_agent.prompts.generation.output_schemas import (
    build_section_patch_output_schema,
)
from src.api.utils.prompt_utils.domain_merge import merge_domain_blocks
from src.api.utils.study_agent_utils.generation.must_cover_checklist_format import (
    checklist_section_id,
    format_must_cover_checklist_line,
)

STEM_ACCURACY_BLOCK = """\
- STEM: equations and reactions belong in formula_blocks and must be correct and dimensionally consistent; worked examples must trace step-by-step to the correct answer; constants must carry correct values and units. Never state a reaction or formula you cannot verify as real. For chemistry: verify the reactants, mechanism, and products are correct for the described reaction type — a correctly formatted but mechanistically wrong reaction is a factual error.
- NO CODE, EVER: this section's output schema has no code_blocks field. If a prior failure cited Python, sympy, scipy, numpy, or any computational code as a substitute for derivation steps, remove the code_block entirely and replace it with sequential formula_block entries — one step per entry, each following from the previous. This applies regardless of whether the linked checklist item's requirement says "derive," "prove," "calculate," or "apply" — there is no STEM verb for which code is an acceptable answer. Retry QC will fail the section again if any code remains."""
PROGRAMMING_ACCURACY_BLOCK = '- Programming: code must be syntactically valid and run correctly on the demonstrated path; no undefined symbols; verify every API call is real for the stated language/version; every code_block must have a non-empty "explanation" field.'
CONCEPTUAL_ACCURACY_BLOCK = """- Conceptual: named facts (dates, people, events, laws, organisations) must be accurate per mainstream record. When fixing thin coverage: add a specific named real-world case — identify the actor, describe the context, and state the verifiable outcome; a sector-level generalisation without a named entity is not an acceptable fix. When fixing a missing causal chain: trace precondition → trigger → mechanism → outcome explicitly; 'X caused Y' without mechanism is not a causal chain. When fixing a missing comparison: name both sides and provide a real named case for each. Do not introduce code_blocks or formula_blocks — all content, including quantitative context, must appear as specific named real-world scenarios in prose. Do not attribute statistics or performance metrics to named organisations unless publicly documented and widely known."""
_ACCURACY_RULES_HEADER = """\
ACCURACY RULES
- Every claim must be true for the specific language, framework, or field in the topic."""
_BASE_SYSTEM_INTRO = """\
You are an expert educator rewriting specific failed sections of a study document.
Mandate: rewrite ONLY the sections listed in <sections_to_fix>. Do not add, remove, or rename sections.
"""
_PATCH_SCOPE_BLOCK = """\
PATCH SCOPE — WHAT YOU MAY TOUCH
Each failure's "evidence" and "corrective_hint" tell you exactly where the defect lives. That is the boundary of your edit, not a starting point for a general cleanup pass.

- A failure is LOCALIZED when its evidence names a specific subsection heading, a specific code_block/formula_block, or a specific claim, sentence, or example. For a localized failure, change ONLY that subsection, block, or claim. Every other subsection, code_block, formula_block, and sentence in current_section_json — including the surrounding prose of the section itself — must be reproduced exactly as given, unchanged.
- A failure is SECTION-WIDE only when its own evidence or corrective_hint describes a defect that cannot be pinned to one part — e.g. it says the section is incoherent, doesn't flow, is disorganized, or is misaligned with its heading or the document outline, or it explicitly says "entire section" / "whole section" / "throughout". Only then may you restructure or rewrite the section beyond the specific spots named elsewhere.
- If a section has several failures and only some are localized, fix each at its named location and leave every subsection with no failure attached to it untouched. One subsection's failure is never license to also revise a different subsection you personally judge to be weak — that is an unrequested change and will fail retry QC.
- Adding content to satisfy a thin-coverage or must_cover gap is allowed, but keep the addition inside or immediately adjacent to the failing subsection — do not touch unrelated subsections to "make room" or "even things out".
- When you cannot tell whether a failure is localized or section-wide, treat it as localized. The narrower edit is always the safe default.
"""
_FAILURE_REMEDIATION_BLOCK = """\
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
8. Every subsection, code_block, and formula_block not named by a failure's evidence matches current_section_json exactly — no incidental rewording, reordering, or "improvement".
9. Any change extending beyond a failure's named location is justified by that same failure's evidence or corrective_hint explicitly describing a section-wide problem.
10. JSON is valid.
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
        _BASE_SYSTEM_INTRO
        + build_section_patch_output_schema(domain)
        + "\n"
        + _PATCH_SCOPE_BLOCK
        + _FAILURE_REMEDIATION_BLOCK
        + build_accuracy_rules_block(domain)
        + "\n\n"
        + _SUBSTANCE_RULES_BLOCK
        + _FINAL_CHECK_BLOCK
    )


# Legacy constant for testing backward-compatibility
_BASE_SYSTEM = _build_base_system("")


def build_system_prompt(*, has_reference: bool, domain: str | None = None) -> str:
    return _build_base_system(domain) + (
        _REFERENCE_ADDENDUM if has_reference else _NO_REFERENCE_ADDENDUM
    )


def _subsection_remediation_targets(
    section_failures: list[dict],
) -> dict[str, list[str]]:
    """Map section_id → subsection headings parsed from failure evidence strings.

    Parses deterministic ``_location_evidence`` format:
    ``Section 'X', subsection 'Y': detail`` via ``subsection_headings_from_evidence``.
    LLM evidence may mention subsections in other phrasing — not guaranteed to match.
    """
    from src.api.utils.study_agent_utils.quality_check_utils.document.document_merge import (
        subsection_targets_from_failures,
    )

    return subsection_targets_from_failures(section_failures)


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
    """Render ``<sections_to_fix>`` JSON for the section-rework user prompt.

    For each failure bundle, embeds full ``current_section_json`` from the live
    document, pared-down ``failures`` list, and optional ``subsections_to_fix``
    when equation-in-prose failures name a subsection heading.
    """
    from src.api.utils.study_agent_utils.quality_check_utils.document.document_merge import (
        extract_sections_by_ids,
        subsection_targets_from_failures,
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
    subsection_targets = subsection_targets_from_failures(section_failures)
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
        "\nRewrite ONLY the sections in <sections_to_fix>. Within each section, change only "
        "what each failure's evidence or corrective_hint names — every other subsection, "
        "code_block, and formula_block must come back exactly as given in current_section_json. "
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
