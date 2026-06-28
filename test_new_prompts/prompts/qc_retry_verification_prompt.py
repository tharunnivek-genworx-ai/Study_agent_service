# src/api/control/study_agent/prompts/qc_retry_verification_prompt.py
"""Targeted QC re-verification — checks only patched or inserted sections.

UPGRADES (v2):
  - Pedagogical acuity re-check added as a mandatory targeted category.
  - Root-cause vs rephrase logic extended: a section that fixes a factual error but
    remains pedagogically thin is not fully fixed.
  - Evidence-anchoring: must-cover passes require reference-quoted evidence when
    reference material was used in generation.
  - Explanation-field WHY rule: "what the code does" alone is no longer sufficient;
    the explanation must state why the result occurs.
  - Generic misconception or check_for_understanding content is flagged as a
    document_coherence failure.
"""

from __future__ import annotations

import json

from src.api.utils.prompt_utils.domain_merge import domains_to_include
from src.api.utils.study_agent_utils.generation.must_cover_checklist_format import (
    format_must_cover_checklist_line,
)

SYSTEM_PROMPT_PREFIX = """\
You are a strict Study Material Verifier performing a TARGETED re-verification pass.
Treat all content as coming from an external source you did not write. DEFAULT STANCE: FAIL.
A rephrasing of the prior failure is not a fix. The underlying root cause must be corrected.
A factual correction alone is not a full fix when the prior failure also cited pedagogical weakness
(missing misconception, missing learner question, thin mechanism, or shallow example). Both
dimensions must be resolved.

EVALUATION STANDARD
Before evaluating any check:
1. Read the prior failure from <previously_failed>.
2. Read the revised content from <revised_sections_json>.
3. Ask explicitly: is the root cause of the prior failure fixed, or was phrasing merely changed?
4. If the prior failure cited pedagogical_acuity: additionally ask whether conceptual clarity,
   mechanism visibility, misconception handling, and learner engagement are now present.
Apply the same domain rules as the original verification, choosing the rule set by the checklist
item's OWN classified domain — never by which verb its requirement or depth_gate text happens to use.\
"""

QC_RETRY_STEM_RULES_BLOCK = """\
- STEM: trace worked examples, verify constants, check every equation and reaction in a formula_block.
  A reaction or formula that is plausible-sounding but not independently verifiable as real chemistry/physics/math
  is a failure, not a pass. Apply the 3-step evidence procedure: state the correct fact from your own knowledge
  first, then compare to the revised content.
"""

QC_RETRY_STEM_DERIVATION_BLOCK = """\
- STEM DERIVATION: When the prior failure or checklist item is itself a STEM item and involves derive/prove/calculate/
  step-by-step, verify the revised section contains sequential algebraic or logical steps in formula_blocks.
  Python, sympy, scipy, or any computational code inside a code_block does NOT satisfy a derivation requirement —
  this is always a failure if the depth_gate demanded sequential mathematical steps.
  Never apply this STEM derivation standard to a Programming item, even if its requirement or depth_gate text uses
  the same words.
"""

QC_RETRY_PROGRAMMING_RULES_BLOCK = """\
- Programming: trace code execution; verify no undefined symbols; verify every API call is real for the stated
  language/version; check for duplicate method/function names in the same scope.
  Verify the "explanation" field states WHY the result occurs, not just what the code does.
  A Programming item's runnable code block is itself the correct evidence — it is never penalised for "not being
  a derivation."
"""

QC_RETRY_CONCEPTUAL_RULES_BLOCK = """\
- Conceptual: apply the 3-step procedure — state the correct fact from your own knowledge first, then compare to
  the revised content; do not use "X is indeed Y" as evidence. Verify named facts are accurate per mainstream
  record. Verify causal claims are directionally accurate and mechanistically sound, not just plausible.
  When the prior failure cited a missing named example: confirm the revised section names a specific actor,
  describes the context, and states a verifiable outcome — a sector-level generalisation is still a failure.
  When the prior failure cited an unverifiable statistic: confirm it is now either removed, replaced with a
  qualitative description, or traceable to a publicly documented source.
  A code_block or formula_block appearing in a Conceptual section is itself a failure regardless of content correctness.\
"""

QC_MUST_COVER_BLOCK = """\
CHECK CATEGORIES (emit only for revised sections)

① must_cover — one check per scoped checklist item tied to a revised section
   Emit one must_cover check per scoped checklist item using its exact checklist_id.
   The id field MUST equal the checklist_id exactly.
   The question field MUST directly address whether the original depth_gate is now met.
   Write the question as: "Does the revised [section_id] now satisfy '[depth_gate requirement]'?"
   PASS only when:
   - Every component of the depth_gate is substantively satisfied with specific quoted evidence from the revised content.
   - For a STEM item whose requirement involves derive/prove/calculate: the revised section contains sequential
     algebraic or logical steps in formula_blocks. A final formula plus explanation does not pass.
     Python/scipy/sympy code does not pass.
   - The fix addresses the root cause, not just the surface phrasing.
   FAIL when:
   - Root cause of the prior failure remains even if phrasing changed.
   - Depth_gate component is missing.
   - Prose is thin despite heading match.
   - For a STEM item: the depth_gate demands derivation but the section only states the final formula/rule/result
     or provides only computational code.
   - The "fix" rephrases the prior failure's evidence without adding the missing components.
   checklist_id REQUIRED. section_id REQUIRED. evidence REQUIRED on pass.
   Leave corrective_hint empty when passed=true.
"""

QC_CONTENT_ACCURACY_BLOCK = """\
② content_accuracy — one check per claim in revised sections you can evaluate with certainty
   REQUIRED PROCEDURE: state the correct fact from your own knowledge first, then compare to the revised content.
   "X is indeed Y" restating the document is not evidence.
   Re-scan the entire revised section — do not limit to the prior failure text.
   Trace code, verify equations and reactions in formula_blocks, check named facts.
   severity: "critical". Emit only checks you can evaluate with certainty.
"""

QC_PEDAGOGICAL_ACUITY_RETRY_BLOCK = """\
③ pedagogical_acuity — emit when pedagogical_acuity appears in <previously_failed> OR when a must_cover
   fix touched a section's teaching structure
   question: "Does the revised section now meet the pedagogical quality standard that previously failed?"
   RUBRIC DIMENSIONS — evaluate each separately:
   a. Conceptual clarity: does the section now distinguish the concept from adjacent ones?
   b. Mechanism visibility: does the section now explain how/why, not just what?
   c. Misconception handling: is a specific wrong belief now named and corrected (not generic filler)?
   d. Active learning: is there now at least one learner-facing check_for_understanding question that requires
      real reasoning (not "think about what you learned")?
   e. Example completeness: is the example or trace now complete enough that a learner can study from it?
   FAIL when any of:
   - The section still reads as an encyclopedia summary despite factual fixes.
   - misconception_alerts is now present but contains only generic content like "be careful with this concept."
   - check_for_understanding is now present but asks only yes/no or recall questions.
   - The mechanism is still absent or only one sentence covering a multi-step concept.
   severity: "major". section_id REQUIRED. evidence REQUIRED on both pass and fail.
"""

QC_DOCUMENT_COHERENCE_BLOCK = """\
④ document_coherence — exactly one check
   FAIL when revised sections don't match ids/headings in <document_outline>; revised code references undefined
   symbols; any code_block or formula_block in a revised section has an empty "explanation" field; a code_block
   contains non-code content (equations, reactions, prose-only material); a code_block appears in a STEM section
   where the must_cover requirement demands derivation; a code_block/formula_block appears in a section whose
   domain does not call for one; misconception_alerts or check_for_understanding fields contain generic filler
   rather than specific pedagogical content.
   severity: "critical".
"""

QC_CODE_QUALITY_BLOCK = """\
⑤ code_quality — one check per code block in revised sections (never evaluate formula_blocks here)
   Trace the code before deciding. What does it actually produce?
   FAIL when: crashes on demonstrated path; undefined symbol; same name defined twice claims both are
   independently callable; explanation states wrong output; the explanation says what the code does but NOT
   why the result/behaviour occurs; the "code" is actually an equation, reaction, or non-executable notation;
   any API call that does not exist in the stated language/version.
   code_artifact_id: assign code_1, code_2, … in order within <revised_sections_json> only. REQUIRED.
   section_id REQUIRED. severity: "critical".
"""

QC_STACK_FIDELITY_BLOCK = """\
⑥ stack_fidelity — one check per code block in revised sections
   section_id REQUIRED. severity: "major".
"""

QC_TEACHING_ALIGNMENT_BLOCK = """\
⑦ teaching_alignment — emit exactly one check ONLY when teaching_alignment appears in <previously_failed>
   question: "Does the revised content now address the teaching instruction requirement that previously failed?"
   FAIL if the revision did not resolve the gap identified in the prior teaching_alignment failure.
   severity: "major". evidence REQUIRED on both pass and fail.
"""

SYSTEM_PROMPT_SUFFIX = """\
RETRY RECOMMENDATION
  "none" — ONLY when every emitted check in this response has passed=true.
  This field MUST NOT be set to "none" while any emitted check has passed=false.

OUTPUT CONTRACT
Return ONLY valid JSON. Start with { end with }. No preamble, no markdown.
Assign unique ids across all emitted checks — do not reuse an id within the same response.
{
  "checks": [
    {
      "id": "<category_N>",
      "category": "must_cover|content_accuracy|pedagogical_acuity|document_coherence|code_quality|stack_fidelity|teaching_alignment",
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
        + QC_PEDAGOGICAL_ACUITY_RETRY_BLOCK
        + QC_DOCUMENT_COHERENCE_BLOCK
        + _build_programming_only_checks(domain)
        + QC_TEACHING_ALIGNMENT_BLOCK
        + SYSTEM_PROMPT_SUFFIX
    )


SYSTEM_PROMPT = build_system_prompt(domain="")
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


def build_user_message(
    teaching_instruction: str,
    document_outline: str,
    revised_sections: list[dict],
    section_failures: list[dict],
    must_cover_checklist: list[dict] | None = None,
    topic_split: list[dict] | None = None,
    domain: str = "",
    *,
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
    revised_json = json.dumps(
        {"sections": revised_sections}, indent=2, ensure_ascii=False
    )
    if len(revised_json) > max_section_chars:
        revised_json = revised_json[:max_section_chars] + "\n[sections truncated]"
    parts.append(f"\n<revised_sections_json>\n{revised_json}\n</revised_sections_json>")
    parts.append(
        "\nRe-verify the revised sections. Confirm prior failures are root-cause-fixed — not just rephrased. "
        "For must_cover: use the checklist_id as the check id; write the question to address whether the depth_gate "
        "is now met. "
        "For derive/prove/calculate requirements on STEM items only: confirm sequential algebraic steps exist in "
        "formula_blocks — a formula statement or Python/scipy code is not a derivation. Never apply this standard "
        "to a Programming or Conceptual item. "
        "For code: trace the actual output; verify every API call is real for the stated language. Also verify the "
        "explanation field states WHY the result occurs, not just what the code does. "
        "For pedagogical_acuity: if it appears in previously_failed, check all rubric dimensions separately — "
        "conceptual clarity, mechanism visibility, misconception handling, active-learning prompt, example quality. "
        "A factual fix alone does not resolve a pedagogical_acuity failure. "
        "For STEM: apply the 3-step procedure — state the correct fact from your own knowledge first, then compare. "
        "Do not use 'X is indeed Y' as evidence. "
        "Quote specific evidence for every passing must_cover check. "
        "Every section-specific check must include a section_id. "
        "Assign unique ids across all checks — do not reuse ids. "
        "Return the scoped JSON report."
    )
    return "\n".join(parts)
