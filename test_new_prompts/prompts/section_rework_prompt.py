# src/api/control/study_agent/prompts/section_rework_prompt.py
"""Section rework prompts — targeted rewrite of specific sections that failed QC.

UPGRADES (v2):
  - Pedagogical rework required: when a prior QC failure cited pedagogical_acuity, the
    rework must address all five rubric dimensions (clarity, mechanism, scaffolding,
    misconception, active-learning).
  - Root-cause mandate extended: "fixing the factual error is not enough if the section
    also failed pedagogically."
  - Explanation-field WHY rule added.
  - Graduated example requirement added for sections with thin examples.
  - Reference-anchored drift prevention.
  - Anti-inflation: newly reworked sections must not shrink or strip pedagogical fields
    as a side-effect of factual corrections.
"""

from __future__ import annotations

from src.api.utils.prompt_utils.domain_merge import merge_domain_blocks
from src.api.utils.study_agent_utils.generation.must_cover_checklist_format import (
    format_must_cover_checklist_line,
)
from test_new_prompts.prompts.generation_prompt import (
    JSON_OUTPUT_SCHEMA,
    format_reference_user_block,
)

STEM_REWORK_BLOCK = (
    "- STEM: trace worked examples step-by-step to correct answers; verify all formula_block equations and reactions "
    "are accurate; state correct constants with units; replace any incorrect content. "
    "When the checklist item or depth_gate demands derivation, proof, or step-by-step calculation, provide "
    "sequential algebraic or logical steps in formula_blocks. Python, sympy, scipy, or any computational code "
    "is not a derivation. "
    "After every corrected derivation or mechanism, include a plain-language 'why this matters' sentence. "
    "If the prior QC failure cited a missing or thin misconception_alerts: add a specific wrong belief and its correction. "
    "If the prior QC failure cited a missing check_for_understanding: add one question asking the learner to predict "
    "a sign, unit, limiting case, or changed assumption."
)

PROGRAMMING_REWORK_BLOCK = (
    "- Programming: for each failed code_block — correct syntax, remove undefined symbols, fix duplicate name issues, "
    "and update the explanation field to state WHY the result/behaviour occurs (not just what the code does). "
    "If the prior failure cited a non-existent API: replace with a verified API and update the code accordingly. "
    "If the prior failure was a pedagogical failure: add or strengthen misconception_alerts (a specific "
    "sync/async, reference-vs-value, or scope trap) and add or strengthen check_for_understanding (a question "
    "asking the learner to mentally trace execution or predict an output)."
)

CONCEPTUAL_REWORK_BLOCK = (
    "- Conceptual: replace any fabricated statistics, invented named examples, or unverifiable causal claims. "
    "Named examples must identify a specific actor, context, and verifiable outcome — not a sector-level generalisation. "
    "Causal chains must trace precondition → trigger → mechanism → outcome explicitly. "
    "Do not add code_blocks or formula_blocks. "
    "If the prior failure cited a missing named example: introduce a real organisation or event with context and outcome. "
    "If the prior failure cited a pedagogical gap: add misconception_alerts with a specific wrong belief and "
    "add check_for_understanding with a question asking the learner to apply, compare, or evaluate."
)

_DOMAIN_RULES_HEADER = "DOMAIN-SPECIFIC REWORK RULES"

_BASE_SYSTEM_PREFIX = f"""\
You are an expert editor fixing specific sections of a study document.
Mandate: rewrite ONLY the sections in <sections_to_rework> that contain errors or QC failures.
Return a complete replacement for each targeted section. Do not return unchanged sections.
{JSON_OUTPUT_SCHEMA}

ROOT CAUSE STANDARD
Do not rephrase the prior failure — fix the underlying cause.
If a prior QC failure cited pedagogical_acuity alongside a factual failure, fixing the factual error alone is not enough.
You must also resolve all cited pedagogical rubric dimensions:
  - Conceptual clarity: the section must distinguish the concept from adjacent ones.
  - Mechanism visibility: the section must explain how/why, not just what.
  - Misconception handling: a specific wrong belief must be named and corrected.
  - Active learning: at least one learner-facing check_for_understanding question requiring real reasoning.
  - Example completeness: the example or trace must be complete enough for independent study.
A rework that leaves any of these dimensions as weak as before is not a full fix.

REWORK SCOPE
- Correct every cited error in <sections_to_rework>.
- Do not silently degrade other parts of a section (e.g. do not shorten a correct mechanism to make room for a fix).
- Do not strip misconception_alerts or check_for_understanding fields that were already present and adequate.
- If a section was not in <sections_to_rework>, do not touch it.

VOLUME PRESERVATION
- After correcting errors, the reworked section must be at least as substantive as the original.
- If the original example was complete and the failure was factual only, fix the factual issue and preserve the full example structure.
- Do not shrink the explanation, mechanism, or examples while correcting a notation or code issue.
"""

_FINAL_CHECK_BLOCK = """\
FINAL CHECK before outputting (do not print):
1. Every cited error in <sections_to_rework> is corrected at the root cause level.
2. Pedagogical rubric dimensions cited in prior failures are resolved (not just patched).
3. For STEM: derivation requirements use sequential algebraic steps in formula_blocks, not Python code.
4. All code_blocks have explanation fields stating WHY the result occurs, not just what.
5. No new undefined symbols, fabricated API names, or unverifiable statistics were introduced.
6. misconception_alerts and check_for_understanding fields are present and contain specific, non-generic content.
7. Volume of reworked sections is equal to or greater than the original.
8. JSON is valid and complete.\
"""

_REFERENCE_ADDENDUM = """\
Reference material is provided. When correcting a section, prefer reference over general knowledge. Do not drift from the reference's framing.\
"""

_NO_REFERENCE_ADDENDUM = """\
No reference material is provided. Correct from authoritative knowledge of the topic.\
"""


def build_domain_rules_block(domain: str | None) -> str:
    return merge_domain_blocks(
        {
            "STEM": STEM_REWORK_BLOCK,
            "Programming": PROGRAMMING_REWORK_BLOCK,
            "Conceptual": CONCEPTUAL_REWORK_BLOCK,
        },
        domain,
        header=_DOMAIN_RULES_HEADER,
        separator="\n",
    )


def _build_base_system(domain: str | None) -> str:
    return (
        _BASE_SYSTEM_PREFIX
        + build_domain_rules_block(domain)
        + "\n\n"
        + _FINAL_CHECK_BLOCK
    )


_BASE_SYSTEM = _build_base_system("")


def build_system_prompt(*, has_reference: bool, domain: str | None = None) -> str:
    return _build_base_system(domain) + (
        _REFERENCE_ADDENDUM if has_reference else _NO_REFERENCE_ADDENDUM
    )


def build_sections_to_rework_block(
    section_failures: list[dict],
    sections_content: list[dict],
) -> str:
    entries = []
    content_map = {s.get("id", ""): s for s in sections_content}
    for bundle in section_failures:
        sid = str(bundle.get("section_id", "")).strip()
        if not sid:
            continue
        section_json = content_map.get(sid, {})
        failures_list = [
            {
                "category": f.get("category", ""),
                "evidence": f.get("evidence", ""),
                "corrective_hint": f.get("corrective_hint", ""),
            }
            for f in (bundle.get("failures") or [])
            if isinstance(f, dict)
        ]
        entry = {
            "section_id": sid,
            "failures": failures_list,
            "current_content": section_json,
        }
        entries.append(entry)
    import json

    payload = json.dumps(entries, indent=2, ensure_ascii=False)
    return f"\n<sections_to_rework>\n{payload}\n</sections_to_rework>"


def build_user_message(
    topic_title: str,
    teaching_instruction: str,
    section_failures: list[dict],
    sections_content: list[dict],
    must_cover_checklist: list[dict] | None = None,
    topic_split: list[dict] | None = None,
    domain: str = "",
    reference_block: str = "",
) -> str:
    parts = [
        f"<topic>{topic_title}</topic>",
        f"\n<teaching_instruction>\n{teaching_instruction}\n</teaching_instruction>",
    ]
    if domain:
        parts.append(f"\n<domain>{domain}</domain>")
    if must_cover_checklist:
        lines = "\n".join(
            format_must_cover_checklist_line(item) for item in must_cover_checklist
        )
        parts.append(f"\n<must_cover_checklist>\n{lines}\n</must_cover_checklist>")
    if topic_split:
        split_lines = "\n".join(
            f"  - [{e.get('id', '')}] {e.get('heading', '')} — pedagogy: {e.get('pedagogy_intent', '')}"
            for e in topic_split
        )
        parts.append(f"\n<topic_split>\n{split_lines}\n</topic_split>")
    parts.append(build_sections_to_rework_block(section_failures, sections_content))
    if reference_block:
        parts.append(reference_block)
    parts.append(
        "\nRewrite each targeted section to correct every cited failure at the root cause level. "
        "Do not rephrase — fix the underlying issue. "
        "If a cited failure includes pedagogical_acuity, resolve all five rubric dimensions: "
        "conceptual clarity, mechanism, misconception correction, learner check question, example completeness. "
        "For STEM derivation requirements: provide sequential algebraic steps in formula_blocks — not Python. "
        "All explanation fields must state WHY the result occurs, not just what the code/formula does. "
        "Preserve or strengthen misconception_alerts and check_for_understanding; do not strip them. "
        "Return the reworked sections JSON."
    )
    return "\n".join(parts)


def format_reference_block(
    extracted_reference_text: str, *, has_reference: bool
) -> str:
    return format_reference_user_block(
        extracted_reference_text, has_reference=has_reference
    )
