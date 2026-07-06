# src/api/control/study_agent/prompts/qc_retry_verification_prompt.py
"""Targeted QC re-verification — checks only patched or inserted sections."""

from __future__ import annotations

import json
from typing import Any

from src.api.utils.prompt_utils.domain_merge import domains_to_include
from src.api.utils.study_agent_utils.generation.must_cover_checklist_format import (
    format_must_cover_checklist_line,
)

SYSTEM_PROMPT_PREFIX = """\
You are a strict Study Material Verifier performing a TARGETED re-verification pass.
Treat all content as coming from an external source you did not write. DEFAULT STANCE: FAIL.
A rephrasing of the prior failure is not a fix. The underlying root cause must be corrected.
EVALUATION STANDARD
Before evaluating any check:
1. Read the prior failure from <previously_failed>.
2. Read the revised content from <revised_sections_json>.
3. Ask explicitly: is the root cause of the prior failure fixed, or was phrasing merely changed?
Apply the same domain rules as the original verification, choosing the rule set by the checklist item's OWN classified domain — never by which verb its requirement or depth_gate text happens to use ("trace," "step-by-step," and "calculate" describe code execution in a Programming item and an algebraic derivation in a STEM item; the word alone never decides which rule applies):
"""
QC_RETRY_STEM_RULES_BLOCK = """\
- STEM: trace worked examples, verify constants, check every equation and reaction in a formula_block. A reaction or formula that is plausible-sounding but not independently verifiable as real chemistry/physics/math is a failure, not a pass. Apply the 3-step evidence procedure: state the correct fact from your own knowledge first, then compare to the revised content.
"""
QC_RETRY_STEM_DERIVATION_BLOCK = """\
- STEM CODE RULE: any STEM-classified section that contains a code_block fails — unconditionally, regardless of
  which verb its checklist item uses (derive, prove, calculate, apply, determine, solve, trace, step-by-step). This
  applies even when the code_block belongs to a section you were NOT asked to re-verify by name — see GLOBAL SCAN
  below. Never apply this STEM standard to a Programming item, even if its text uses the same words.
"""
QC_RETRY_PROGRAMMING_RULES_BLOCK = """\
- Programming: trace code execution; verify no undefined symbols; verify every API call is real for the stated language/version; check for duplicate method/function names in the same scope. A Programming item's runnable code block is itself the correct evidence — it is never penalised for "not being a derivation."
"""
QC_RETRY_CONCEPTUAL_RULES_BLOCK = """\
- Conceptual: apply the 3-step procedure — state the correct fact from your own knowledge first, then compare to the revised content; do not use "X is indeed Y" as evidence. Verify named facts (dates, people, events, laws, organisations) are accurate per mainstream record. Verify causal claims are directionally accurate and mechanistically sound, not just plausible. When the prior failure cited a missing named example: confirm the revised section names a specific actor, describes the context, and states a verifiable outcome — a sector-level generalisation ("many companies", "government agencies") is still a failure even after revision. When the prior failure cited an unverifiable statistic: confirm it is now either removed, replaced with a qualitative description, or traceable to a publicly documented source. A code_block or formula_block appearing in a Conceptual section is itself a failure regardless of content correctness.\
"""
QC_GLOBAL_SCAN_BLOCK = """\
GLOBAL SCAN — run before scoring any other category, every retry pass, with no exceptions
<revised_sections_json> may contain sections beyond the ones the patch targeted (extraction re-scans the full
document on every pass). For every section present in <revised_sections_json>, regardless of whether it appears in
<previously_failed>:
- If its domain is STEM and it contains any code_block: emit a document_coherence check with passed=false,
  severity="critical", section_id set to that section, and evidence quoting the offending code. This check fires
  even when that section was never targeted by this retry and was not the source of the prior failure being
  re-verified — a structural violation does not get a pass just because nobody patched it this round.
- If a must_cover item is linked to that same section, also emit a must_cover check with passed=false for it,
  checklist_id set to the linked item, explaining that a STEM section may not contain code regardless of what the
  prior pass concluded about that item.
Do this for every qualifying section before moving to the scoped categories below — a stale pass from a prior round
is never carried forward silently; it must be re-asserted as failed here if the violation still exists.
"""

QC_MUST_COVER_BLOCK = """\
CHECK CATEGORIES
① must_cover — one check per scoped checklist item tied to a revised section, PLUS any check emitted by GLOBAL SCAN above
   Emit one must_cover check per scoped checklist item using its exact checklist_id.
   The id field MUST equal the checklist_id exactly. The question field MUST directly address whether the original depth_gate is now met — do NOT substitute with a generic "Is the root cause of the prior failure fixed?" question. Write the question as: "Does the revised [section_id] now satisfy '[depth_gate requirement]'?"
   PASS only when:
   - Every component of the depth_gate is substantively satisfied with specific quoted evidence from the revised content.
   - For a STEM item whose requirement involves derive/prove/calculate: the revised section contains sequential algebraic or logical steps in formula_blocks. A final formula plus explanation does not pass. Python/scipy/sympy code does not pass. (This standard applies only to STEM items — for a Programming item, a runnable code block plus a correct behavioural explanation is the right and sufficient evidence, even if its requirement text contains the same words.)
   FAIL when:
   - Root cause of the prior failure remains even if phrasing changed.
   - Depth_gate component is missing.
   - Prose is thin despite heading match.
   - For a STEM item: the depth_gate demands derivation, proof, or step-by-step calculation, but the section only states the final formula/rule/result, or provides only computational code. (Never fail a Programming item on this basis.)
   - The "fix" rephrases the prior failure's evidence without adding the missing components.
   checklist_id REQUIRED. section_id REQUIRED. evidence REQUIRED on pass.
   Leave corrective_hint empty when passed=true.
"""
QC_CONTENT_ACCURACY_BLOCK = """\
② content_accuracy — one check per claim in revised sections you can evaluate with certainty
   REQUIRED PROCEDURE: state the correct fact from your own knowledge first, then compare to the revised content. "X is indeed Y" restating the document is not evidence.
   Re-scan the entire revised section — do not limit to the prior failure text.
   Trace code, verify equations and reactions in formula_blocks, check named facts.
   severity: "critical". Emit only checks you can evaluate with certainty.
"""
QC_DOCUMENT_COHERENCE_BLOCK = """\
③ document_coherence — one check per <document_outline> mismatch or schema violation, PLUS the checks already
   emitted by GLOBAL SCAN above (do not duplicate a GLOBAL SCAN finding here — it already counts)
   FAIL when revised sections don't match ids/headings in <document_outline>; revised code references undefined
   symbols; any code_block or formula_block in a revised section has an empty "explanation" field; a code_block
   contains non-code content; a code_block/formula_block appears in a section whose domain does not call for one.
   severity: "critical".
"""
QC_CODE_QUALITY_BLOCK = """\
④ code_quality — one check per code block in revised sections (never evaluate formula_blocks here — verify those under content_accuracy)
   Trace the code before deciding. What does it actually produce?
   FAIL when: crashes on demonstrated path; undefined symbol; same name defined twice claims both are independently callable; explanation states wrong output; the "code" is actually an equation, reaction, or non-executable notation; any API call that does not exist in the stated language/version.
   code_artifact_id: assign code_1, code_2, … in order within <revised_sections_json> only. REQUIRED.
   section_id REQUIRED. severity: "critical".
"""
QC_STACK_FIDELITY_BLOCK = """\
⑤ stack_fidelity — one check per code block in revised sections
   section_id REQUIRED. severity: "major".
"""
QC_TEACHING_ALIGNMENT_BLOCK = """\
⑥ teaching_alignment — emit exactly one check when <prior_teaching_alignment_failure> is present OR teaching_alignment appears in <previously_failed>
   question: "Does the revised content now address the teaching instruction requirement that previously failed?"
   Re-read the teaching instruction and the full document outline plus all revised sections. Fail if gaps cited in the prior failure remain, or if patched sections still do not meet the instruction's clarity/depth requirements.
   severity: "major". evidence REQUIRED on both pass and fail.
"""
SYSTEM_PROMPT_SUFFIX = """\
RETRY RECOMMENDATION
  "none" — ONLY when every emitted check in this response has passed=true. This field MUST NOT be set to "none" while any emitted check has passed=false, regardless of any other reasoning.
OUTPUT CONTRACT
Return ONLY valid JSON. Start with { end with }. No preamble, no markdown.
Assign unique ids across all emitted checks — do not reuse an id within the same response (e.g. emit content_accuracy_1, content_accuracy_2, never two checks both named content_accuracy_1).
{
  "checks": [
    {
      "id": "<category_N>",
      "category": "must_cover|content_accuracy|document_coherence|code_quality|stack_fidelity|teaching_alignment",
      "question": "<binary yes/no>",
      "passed": true|false,
      "severity": "critical|major|minor",
      "evidence": "<specific quote or description>",
      "corrective_hint": "<one-sentence fix — required when passed=false>",
      "section_id": "<required for all section-specific checks>",
      "checklist_id": "<required for must_cover>",
      "code_artifact_id": "<required for code checks>"
    }
  ],
  "hallucination_risk": "none|low|medium|high",
  "is_refusal": false,
  "issues": ["<specific problem>"],
  "corrective_instructions": "<precise actionable paragraph or empty string>",
  "summary": "<2-3 sentence plain-English summary>",
  "retry_recommendation": {
    "mode": "none|section_patch|section_insert|section_patch_then_insert|full_regeneration",
    "failed_section_ids": [],
    "missing_checklist_ids": [],
    "rationale": "<why this mode>"
  }
}\
"""


def _build_evaluation_standard_block(domain: str | None) -> str:
    included = domains_to_include(domain)
    parts = [SYSTEM_PROMPT_PREFIX]
    if "STEM" in included:
        parts.append(QC_RETRY_STEM_RULES_BLOCK)
        parts.append(QC_RETRY_STEM_DERIVATION_BLOCK)
    if "Programming" in included:
        parts.append(QC_RETRY_PROGRAMMING_RULES_BLOCK)
    if "Conceptual" in included:
        parts.append(QC_RETRY_CONCEPTUAL_RULES_BLOCK)
    parts.append(QC_GLOBAL_SCAN_BLOCK)
    return "".join(parts)


def _build_programming_only_checks(domain: str | None) -> str:
    if "Programming" not in domains_to_include(domain):
        return ""
    return QC_CODE_QUALITY_BLOCK + QC_STACK_FIDELITY_BLOCK


def build_system_prompt(domain: str | None = None) -> str:
    return (
        _build_evaluation_standard_block(domain)
        + QC_MUST_COVER_BLOCK
        + QC_CONTENT_ACCURACY_BLOCK
        + QC_DOCUMENT_COHERENCE_BLOCK
        + _build_programming_only_checks(domain)
        + QC_TEACHING_ALIGNMENT_BLOCK
        + SYSTEM_PROMPT_SUFFIX
    )


REPROMPT_SYSTEM = (
    "Your previous response was not valid JSON. "
    "Return ONLY the JSON object. Start with { and end with }. No markdown, no commentary."
)


def build_previously_failed_block(section_failures: list[dict]) -> str:
    entries: list[dict] = []
    for bundle in section_failures:
        section_id = str(bundle.get("section_id", "")).strip()
        if not section_id:
            continue
        failures = bundle.get("failures") or []
        entries.append(
            {
                "section_id": section_id,
                "heading": bundle.get("heading", ""),
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
        )
    payload = json.dumps(entries, indent=2, ensure_ascii=False)
    return f"\n<previously_failed>\n{payload}\n</previously_failed>"


def build_prior_teaching_alignment_block(
    prior_teaching_alignment: dict[str, Any] | None,
) -> str:
    if not prior_teaching_alignment:
        return ""
    payload = json.dumps(prior_teaching_alignment, indent=2, ensure_ascii=False)
    return f"\n<prior_teaching_alignment_failure>\n{payload}\n</prior_teaching_alignment_failure>"


def extract_prior_teaching_alignment_failure(
    qc_result: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Return the most recent failed document-level teaching_alignment check."""
    if not isinstance(qc_result, dict):
        return None
    for check in qc_result.get("checks") or []:
        if not isinstance(check, dict):
            continue
        if str(check.get("category", "")) != "teaching_alignment":
            continue
        if check.get("passed", True):
            continue
        if str(check.get("section_id", "") or "").strip():
            continue
        return check
    return None


def build_user_message(
    teaching_instruction: str,
    document_outline: str,
    revised_sections: list[dict],
    section_failures: list[dict],
    must_cover_checklist: list[dict] | None = None,
    topic_split: list[dict] | None = None,
    domain: str = "",
    *,
    prior_teaching_alignment_failure: dict[str, Any] | None = None,
    max_section_chars: int = 40000,
) -> str:
    parts = [
        f"\n<teaching_instruction>\n{teaching_instruction}\n</teaching_instruction>",
        f"\n<document_outline>\n{document_outline.strip()}\n</document_outline>",
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
            f"  - [{e.get('id', '')}] {e.get('heading', '')}" for e in topic_split
        )
        parts.append(f"\n<topic_split>\n{split_lines}\n</topic_split>")
    parts.append(build_previously_failed_block(section_failures))
    prior_ta_block = build_prior_teaching_alignment_block(
        prior_teaching_alignment_failure
    )
    if prior_ta_block:
        parts.append(prior_ta_block)
    revised_json = json.dumps(
        {"sections": revised_sections}, indent=2, ensure_ascii=False
    )
    if len(revised_json) > max_section_chars:
        revised_json = revised_json[:max_section_chars] + "\n[sections truncated]"
    parts.append(f"\n<revised_sections_json>\n{revised_json}\n</revised_sections_json>")
    parts.append(
        "\nRun GLOBAL SCAN across every section in <revised_sections_json> before scoring scoped checklist items, "
        "even sections not named in <previously_failed>. "
        "Re-verify the revised sections. Confirm prior failures are root-cause-fixed — not just rephrased. "
        "For must_cover: use the checklist_id as the check id; write the question to address whether the depth_gate is now met. "
        "For STEM items: any code_block in a STEM section is always a failure — unconditionally. "
        "For code: trace the actual output; verify every API call is real for the stated language. "
        "For STEM: apply the 3-step procedure — state the correct fact from your own knowledge first, then compare. Do not use 'X is indeed Y' as evidence. "
        "Quote specific evidence for every passing must_cover check. "
        "Every section-specific check must include a section_id. "
        "Assign unique ids across all checks — do not reuse ids. "
        "Return the scoped JSON report."
    )
    return "\n".join(parts)
