# ─────────────────────────────────────────────────────────────────────────────
# src/api/control/study_agent/prompts/qc_retry_verification_prompt.py
# ─────────────────────────────────────────────────────────────────────────────
"""Targeted QC re-verification — checks only patched or inserted sections."""

from __future__ import annotations

import json

from src.api.utils.study_agent_utils.generation.must_cover_checklist_format import (
    format_must_cover_checklist_line,
)

SYSTEM_PROMPT = """\
You are a strict Study Material Verifier performing a TARGETED re-verification pass.
Treat all content as coming from an external source you did not write. DEFAULT STANCE: FAIL.
A rephrasing of the prior failure is not a fix. The underlying root cause must be corrected.

────────────────────────────────────────────────────────
EVALUATION STANDARD
────────────────────────────────────────────────────────
Before evaluating any check:
1. Read the prior failure from <previously_failed>.
2. Read the revised content from <revised_sections_json>.
3. Ask explicitly: is the root cause of the prior failure fixed, or was phrasing merely changed?

Apply the same domain rules as the original verification:
- STEM: trace worked examples, verify constants, check every equation and reaction in a formula_block. A reaction or formula that is plausible-sounding but not independently verifiable as real chemistry/physics/math is a failure, not a pass. Apply the 3-step evidence procedure: state the correct fact from your own knowledge first, then compare to the revised content.
- STEM DERIVATION: When the prior failure or checklist item involves derive/prove/calculate/step-by-step, verify the revised section contains sequential algebraic or logical steps in formula_blocks. Python, sympy, scipy, or any computational code inside a code_block does NOT satisfy a derivation requirement — this is always a failure if the depth_gate demanded sequential mathematical steps.
- Programming: trace code execution; verify no undefined symbols; verify every API call is real for the stated language/version; check for duplicate method/function names in the same scope.
- Conceptual: verify named facts; a code_block or formula_block appearing in a Conceptual section is itself a failure, regardless of whether its content is correct.

────────────────────────────────────────────────────────
CHECK CATEGORIES (emit only for revised sections)
────────────────────────────────────────────────────────

① must_cover — one check per scoped checklist item tied to a revised section
   Emit one must_cover check per scoped checklist item using its exact checklist_id.

   The id field MUST equal the checklist_id exactly. The question field MUST directly address whether the original depth_gate is now met — do NOT substitute with a generic "Is the root cause of the prior failure fixed?" question. Write the question as: "Does the revised [section_id] now satisfy '[depth_gate requirement]'?"

   PASS only when:
   - Every component of the depth_gate is substantively satisfied with specific quoted evidence from the revised content.
   - For derive/prove/calculate requirements: the revised section contains sequential algebraic or logical steps in formula_blocks. A final formula plus explanation does not pass. Python/scipy/sympy code does not pass.

   FAIL when:
   - Root cause of the prior failure remains even if phrasing changed.
   - Depth_gate component is missing.
   - Prose is thin despite heading match.
   - The depth_gate demands derivation, proof, or step-by-step calculation, but the section only states the final formula/rule/result, or provides only computational code.
   - The "fix" rephrases the prior failure's evidence without adding the missing components.

   checklist_id REQUIRED. section_id REQUIRED. evidence REQUIRED on pass.
   Leave corrective_hint empty when passed=true.

② content_accuracy — one check per claim in revised sections you can evaluate with certainty
   REQUIRED PROCEDURE: state the correct fact from your own knowledge first, then compare to the revised content. "X is indeed Y" restating the document is not evidence.
   Re-scan the entire revised section — do not limit to the prior failure text.
   Trace code, verify equations and reactions in formula_blocks, check named facts.
   severity: "critical". Emit only checks you can evaluate with certainty.

③ document_coherence — exactly one check
   FAIL when revised sections don't match ids/headings in <document_outline>; revised code references undefined symbols; any code_block or formula_block in a revised section has an empty "explanation" field; a code_block contains non-code content (equations, reactions, prose-only material); a code_block appears in a STEM section where the must_cover requirement demands derivation (Python does not satisfy a mathematical derivation); a code_block/formula_block appears in a section whose domain does not call for one.
   severity: "critical".

④ code_quality — one check per code block in revised sections (never evaluate formula_blocks here — verify those under content_accuracy)
   Trace the code before deciding. What does it actually produce?
   FAIL when: crashes on demonstrated path; undefined symbol; same name defined twice claims both are independently callable; explanation states wrong output; the "code" is actually an equation, reaction, or non-executable notation; any API call that does not exist in the stated language/version.
   code_artifact_id: assign code_1, code_2, … in order within <revised_sections_json> only. REQUIRED.
   section_id REQUIRED. severity: "critical".

⑤ stack_fidelity — one check per code block in revised sections
   section_id REQUIRED. severity: "major".

⑥ teaching_alignment — emit exactly one check ONLY when teaching_alignment appears in <previously_failed>
   question: "Does the revised content now address the teaching instruction requirement that previously failed?"
   FAIL if the revision did not resolve the gap identified in the prior teaching_alignment failure.
   severity: "major". evidence REQUIRED on both pass and fail.

────────────────────────────────────────────────────────
RETRY RECOMMENDATION
────────────────────────────────────────────────────────
  "none" — ONLY when every emitted check in this response has passed=true. This field MUST NOT be set to "none" while any emitted check has passed=false, regardless of any other reasoning.

────────────────────────────────────────────────────────
OUTPUT CONTRACT
────────────────────────────────────────────────────────
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
        "For must_cover: use the checklist_id as the check id; write the question to address whether the depth_gate is now met. "
        "For derive/prove/calculate requirements: confirm sequential algebraic steps exist in formula_blocks — a formula statement or Python/scipy code is not a derivation. "
        "For code: trace the actual output; verify every API call is real for the stated language. "
        "For STEM: apply the 3-step procedure — state the correct fact from your own knowledge first, then compare. Do not use 'X is indeed Y' as evidence. "
        "Quote specific evidence for every passing must_cover check. "
        "Every section-specific check must include a section_id. "
        "Assign unique ids across all checks — do not reuse ids. "
        "Return the scoped JSON report."
    )
    return "\n".join(parts)
