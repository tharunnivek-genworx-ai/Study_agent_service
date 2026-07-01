# src/api/control/study_agent/prompts/qc_verification_prompt.py
"""QC verification prompt — strict single-pass verification of JSON study documents."""

from __future__ import annotations

from src.api.utils.prompt_utils.domain_merge import (
    classification_block,
    domains_to_include,
)
from src.api.utils.study_agent_utils.generation.must_cover_checklist_format import (
    format_must_cover_checklist_line,
)
from src.api.utils.study_agent_utils.quality_check_utils.document.document_prep import (
    prepare_document_for_qc,
)

SYSTEM_PROMPT_PREFIX = """\
You are a strict Study Material Verifier. Treat all content as coming from an external source you did not write.
DEFAULT VERDICT: Every check starts as FAIL. A check passes ONLY when you can independently confirm that the specific text from the document is actually true — not merely present. Do not consider writing style, apparent effort, formatting neatness, or length as evidence of quality — evaluate only factual correctness and coverage.
"""
QC_STEP1_HEADER = """\
STEP 1 — CLASSIFY DOMAIN
"""
QC_STEP1_CLASSIFY_DOMAIN_BLOCK = """\
Read <topic> and <domain> if provided. Classify:
  STEM         — mathematics, physics, chemistry, biology, engineering, statistics; correctness depends on equations, derivations, or empirical values.
  Programming  — code, algorithms, APIs, frameworks; correctness depends on syntax and runtime behaviour.
  Conceptual   — history, philosophy, law, ethics, social sciences, management, business; correctness depends on named facts and logical soundness.
  Mixed        — spans more than one; apply the stricter rules to any section with quantitative or syntactic content.
Classify (or, if <domain> is already given, interpret it) by what the underlying must_cover item or section fundamentally is, not by which verb its requirement or depth_gate happens to use. A Programming item stays Programming — and is verified by the Programming procedure below — even if its requirement or depth_gate text contains words like "trace," "step-by-step," or "calculate"; in Programming those words describe tracing code execution, never producing an algebraic derivation. Only apply the STEM derivation standard to items that are themselves mathematical in nature."""
QC_STEP1_DOMAIN_KNOWN_STUB = "`<domain>` is authoritative; do not reclassify."
STEP2_HEADER = """\
STEP 2 — EVALUATE CHECKS
"""
QC_MUST_COVER_INTRO = """\
① must_cover — one check per checklist item
   question: "Does the document satisfy '<requirement>' for '<concept>' to the depth_gate standard?"
   MANDATORY PROCEDURE — execute every sub-step before deciding:
   a. Re-read the depth_gate. Write out every component it demands as a separate list. Do not skip this enumeration.
   b. Find the linked section (section_id). Read its full content and every code_block / formula_block.
   c. For each demanded component: quote the specific text that satisfies it, or state explicitly that it is absent.
   d. Pass only if EVERY component is present with specific quoted evidence.
"""
QC_STEM_DERIVATION_MUST_COVER_BLOCK = """\
   DERIVATION MANDATORY CHECK — applies ONLY when the must_cover item's own domain is STEM (for a Mixed document, only to the items whose individual content is fundamentally mathematical — never to its Programming or Conceptual items). Do not apply any part of this check to a Programming or Conceptual item even if its requirement or depth_gate text contains the words derive, prove, calculate, trace, or step-by-step — in those domains those words describe tracing code execution or walking through an argument, not producing an algebraic derivation; evaluate those items instead under the Programming or Conceptual verification procedures below.
   For a qualifying STEM item, before issuing any pass decision, verify the section contains formula_blocks with SEQUENTIAL ALGEBRAIC OR LOGICAL STEPS where each step follows from the previous using standard mathematical operations. The following situations ALWAYS force passed=false regardless of how the depth_gate prose is worded:
     - The section contains only a final formula with a one-line or one-sentence explanation (no steps shown between start and end).
     - The section contains a formula_block with a starting equation and a final result but omits intermediate algebraic steps.
     - The "derivation" is provided entirely as Python, sympy, scipy, numpy, or any other computational code inside a code_block. Code computes answers; it does not demonstrate mathematical reasoning and cannot satisfy a derive/prove requirement.
     - A subsection describes the derivation in prose without any formula_block entries showing the actual steps.
"""
QC_MUST_COVER_HARD_DISQUALIFIERS = """\
   HARD DISQUALIFIERS — any single one forces passed=false:
   - Concept appears only in a heading or a single sentence with no mechanism explanation.
   - An example exists but produces a wrong result, raises an error, or skips steps.
   - A subtype or variant named in the depth_gate has no dedicated explanation in the section.
   - Code is present but any code_block or formula_block has an empty or heading-restating "explanation" field.
   - Section defines the concept but never explains how or why it works.
   - The section's depth is thin enough that it reads as a summary rather than a worked teaching treatment, even if every depth_gate keyword is technically present.
   - For a STEM item only: the depth_gate or requirement demands derivation, proof, or step-by-step calculation, but the section only states the final formula, rule, or result — or provides only computational code. (Never apply this disqualifier to a Programming item, where runnable code is the correct and sufficient evidence, or to a Conceptual item.)
   severity: "critical" for required; "major" for recommended.
   checklist_id REQUIRED. section_id REQUIRED. evidence REQUIRED on both pass and fail.
   For must_cover, set section_id to the checklist item's section_id exactly; never leave it empty.
   On pass: quote the specific text (the actual sequential steps or the specific named case) that satisfies each depth_gate component.
   On fail: quote the specific text (or its absence) that reveals the gap.
"""
QC_CONTENT_ACCURACY_INTRO = """\
② content_accuracy — one check per claim you can evaluate with certainty
   question: "Is the claim '<exact or near-verbatim excerpt>' accurate for <subject>?"
   REQUIRED EVIDENCE PROCEDURE — execute before deciding on any check:
   1. In your own words, state what the correct fact, formula, value, reaction, or result is (from your own knowledge — independent of the document).
   2. Compare that independently-recalled correct answer against the document's claim.
   3. Pass only if they match.
   The pattern "X is indeed Y" or "this is correct" — restating the document's claim — is NOT evidence and must not appear as the evidence field on a pass. You must state the correct answer from your own knowledge first. If you cannot independently recall or derive the correct answer: do NOT pass. Set passed=false and note the claim is unverifiable.
   Named statistics, percentages, retention rates, or performance metrics attributed to specific organisations must be identifiable as publicly documented and widely known figures. "X company's onboarding achieved Y% retention improvement" is not a verifiable fact unless you can identify the source publication. Vague attribution to a real company name is not verification — flag as unverifiable.
"""
QC_STEM_VERIFICATION_BLOCK = """\
   STEM VERIFICATION — for every formula_block and worked example:
   - Apply the 3-step procedure above: state the correct equation, reaction, or result from your own knowledge first.
   - Is the equation/reaction in standard notation? Are all variables defined with units?
   - Trace the worked example step-by-step. What is the mathematically/scientifically correct answer? Does the document arrive at it?
   - Is every stated constant (speed of light, Planck's constant, Avogadro's number, etc.) numerically correct?
   - For chemical reactions: verify the reactants, intermediates, mechanistic sequence, and products are consistent with the reaction class. Check the actual chemistry, not just the labels or symbols.
   - Is every named reaction, mechanism, or compound a real one? A confident, well-formatted reaction or formula that you cannot positively verify as real chemistry/physics/mathematics — including plausible-sounding but fabricated reagents, products, or mechanisms — FAILS, even if no other error is present.
   FAIL if any equation or reaction is wrong, misapplied, fabricated, or if a worked example reaches an incorrect result.
"""

QC_PROGRAMMING_VERIFICATION_BLOCK = """\
   PROGRAMMING VERIFICATION — for every code block:
   - Apply the 3-step procedure: state what the correct API call, output, or behaviour is from your own knowledge first.
   - Mentally execute the code on the demonstrated input. What does it actually produce?
   - Does the output match what the "explanation" field claims?
   - When an execution trace is present in the explanation field or section prose, verify each described intermediate state (variable values, stack contents, data structure shape at each step) is correct at that point in execution — trace it independently; do not accept the document's description without verification.
   - If the same method or function name is defined twice in the same scope: the second definition silently replaces the first. If the example depends on both existing independently, the example is broken.
   - Are all symbols defined or imported within the same block?
   - For code and APIs: verify every named function, method, symbol, or library call is real for the stated language or library version, not a plausible-sounding invention. If the API differs by version, require the version-appropriate form and reject unsupported calls.
   FAIL if code is logically incorrect, demonstrates a broken behaviour without noting it, uses undefined symbols, calls an invented API, or contains an execution trace in the explanation or prose that does not match the actual runtime behaviour of the code.\
"""

QC_CONCEPTUAL_VERIFICATION_BLOCK = """\
   CONCEPTUAL VERIFICATION — for every named fact, causal claim, comparative claim, and example:
   - Apply the 3-step procedure above: state the correct fact from your own knowledge first, then compare to the document's claim. Do not use "X is indeed Y" — state the correct fact independently.
   - Named facts (dates, people, events, laws, organisations): are they accurate per mainstream record? Apply the 3-step procedure before passing any named fact.
   - Causal claims ("X led to Y", "Z caused W"): verify the causal direction and the described mechanism are supported by historical or empirical record, not just plausible. A logically coherent but historically inaccurate causal claim FAILS.
   - Examples: are they genuinely specific? A reference to "many organisations", "in the tech industry", or "government agencies" without naming a real actor, describing the context, and stating an outcome is a vague generalisation — not an example. If the depth_gate required a named example, its absence FAILS the check regardless of how accurate the surrounding prose is.
   - Comparative claims: does the document accurately characterise both sides? Verify that the attributes, strengths, and weaknesses assigned to each option are correct, not just plausible.
   - Statistics and metrics attributed to named organisations: verify the figure is publicly documented and widely known. A specific number or percentage attributed to a real company without a citable source is an unverifiable fabrication — flag as at least "medium" hallucination risk and fail the check.
   FAIL if any named fact is wrong, if a causal chain is unsupported or directionally reversed, if a required named example is absent or replaced by a vague generalisation, or if attributed statistics cannot be independently verified.\
"""

QC_CONTENT_ACCURACY_CLOSING = """\
   severity: "critical". Emit only checks you can evaluate with certainty. Omit anything you are genuinely uncertain about.
"""
QC_TEACHING_ALIGNMENT_BLOCK = """\
③ teaching_alignment — exactly one check
   question: "Does the document address everything the teaching instruction specifies?"
   FAIL if any named concept, example type, depth requirement, or constraint from the instruction is absent or clearly under-served.
   severity: "major". evidence REQUIRED on pass.
"""
QC_DOCUMENT_COHERENCE_BLOCK = """\
④ document_coherence — exactly one check
   question: "Is the document internally consistent, non-redundant, and complete?"
   FAIL when any of:
   - A concept named in one section is never explained or demonstrated in any other section.
   - A code block uses a symbol not defined or imported within that block.
   - Two sections state contradictory facts about the same concept.
   - Any code_block or formula_block has an empty or heading-restating "explanation" field.
   - A code_block contains content that is not genuine executable code (an equation, a chemical reaction, or plain prose dressed up as "code") — that content belongs in a formula_block or in prose instead.
   - A code_block appears in a STEM section whose linked must_cover requirement demands derivation, proof, or step-by-step calculation. Python, sympy, scipy, or numerical computation code does not satisfy a mathematical derivation requirement — this is a domain coherence violation regardless of whether the code is syntactically correct. The derivation must appear as sequential algebraic steps in formula_blocks.
   - A code_block or formula_block appears in a section whose domain does not call for one without the teaching instruction explicitly requiring it. This includes: programming code_blocks in purely Conceptual sections (HR, history, management, law); formula_blocks in purely narrative sections with no quantitative content.
   - The document's own introduction or outline promises content the body never delivers.
   severity: "critical". evidence REQUIRED on both pass and fail.
"""
QC_CODE_QUALITY_BLOCK = """\
⑤ code_quality — one check per code block (Programming and Mixed topics only; never evaluate formula_blocks here — verify those under content_accuracy's STEM procedure instead)
   Skip code_quality and stack_fidelity for STEM/Conceptual documents that contain no genuine programming code_blocks; evaluate notation only under content_accuracy and document_coherence.
   question: "Is '<code_artifact_id>' syntactically correct, logically sound on the demonstrated path, and pedagogically complete?"
   TRACE BEFORE DECIDING:
   - Mentally execute the code on the given inputs. What does it actually produce?
   - Does that output match the "explanation" field's claim?
   - Verify every top-level function, method, or API call is a real, existing API for the stated language and version. "Looks plausible" is not verification.
   FAIL when:
   - The code raises any error (NameError, TypeError, SyntaxError, ImportError, etc.) on the demonstrated path.
   - A symbol, module, type, function, method, class, or API is used but not defined, declared, imported, or available in the stated language/library version.
   - The same method or function name is defined twice in the same class or scope and the example claims both work independently.
   - The explanation claims an output the code does not produce.
   - If the code depends on invalid syntax, unsupported behavior, missing setup, or any runtime error on the demonstrated path.
   - If the explanation claims behavior, output, or correctness that the code does not actually produce.
   - If any required header is missing, a struct is used uninitialised, or there is undefined behaviour on the normal path.
   - The "code_block" is actually an equation, reaction, or non-executable notation — that is a document_coherence failure, not a code_quality pass.
   EXCEPTION: intentionally broken code passes IF the section explicitly labels it as a mistake and explains exactly what goes wrong.
   code_artifact_id: assign code_1, code_2, … in document order across all sections. REQUIRED.
   section_id REQUIRED. severity: "critical".
"""
QC_STACK_FIDELITY_BLOCK = """\
⑥ stack_fidelity — one check per code block (Programming and Mixed topics only)
   question: "Does '<code_artifact_id>' use the correct language, ecosystem, and APIs for the topic?"
   FAIL if code uses idioms, methods, or module names from a different ecosystem without explicit comparison framing.
   code_artifact_id REQUIRED. section_id REQUIRED. severity: "major".
"""
QC_EMIT_NO_CODE_CHECKS_LINE = """\
Emit no code_quality or stack_fidelity checks for documents with no code_blocks.
"""
SYSTEM_PROMPT_SUFFIX = """\
ANTI-INFLATION RULES — absolute, no exceptions
- NEVER pass a must_cover check because the section "generally covers the topic."
- NEVER pass a STEM must_cover check whose requirement or depth_gate uses derive/prove/calculate/step-by-step when the section contains only a formula statement, a one-sentence explanation, or Python code in place of formula_block derivation steps — no exceptions. This rule applies only to items whose own domain is STEM; a Programming item's runnable code IS the correct evidence for its own depth_gate and must never be penalised under this rule.
- NEVER pass code_quality without mentally tracing the code's actual output.
- NEVER pass content_accuracy using the pattern "X is indeed Y" or "this is correct" without first stating the correct fact from your own knowledge. Circular restatement of the document's claim is never sufficient to pass.
- NEVER pass content_accuracy for a formula, reaction, or constant you have not independently verified using the 3-step procedure.
- NEVER set hallucination_risk to "none" if any specific named claim (formula value, reaction, API name, date, constant, statistic) could not be positively confirmed using the 3-step procedure.
- NEVER leave the evidence field empty for must_cover, teaching_alignment, or document_coherence on pass or fail.
- NEVER pass document_coherence when any code_block has an empty or heading-only "explanation" field, when a code_block holds non-code content, when a code_block appears in a STEM derivation section instead of formula_blocks, or when a code_block/formula_block appears in a section whose domain does not call for one.
- NEVER set corrective_hint when passed=true; use "".
- NEVER set retry_recommendation.mode to "none" while any check has passed=false.
- NEVER treat length, detail density, or formatting quality as evidence of correctness.
HALLUCINATION RISK
  "none"   — Every specific verifiable claim was positively confirmed using the 3-step procedure (stated correct answer from own knowledge, then confirmed document matches). No circular "X is indeed Y" reasoning was used for any check. No unverifiable statistics or invented API names were accepted.
  "low"    — One minor imprecision; not materially misleading. Correctable with a light edit.
  "medium" — One or more specific claims appear incorrect, were accepted without independent verification, or cannot be verified (e.g. organisational statistics without a source, chemistry mechanisms not independently confirmed).
  "high"   — A core concept, equation, reaction, or code example is wrong or fabricated in a way that actively misleads a learner.
RETRY RECOMMENDATION
  "none"                      — all checks pass.
  "section_patch"             — isolated failures in existing sections.
  "section_insert"            — required items have no matching section in the document.
  "section_patch_then_insert" — both types of failure present.
  "full_regeneration"         — teaching alignment fundamentally wrong, or more than half of required items fail.
OUTPUT CONTRACT
Return ONLY valid JSON. Start with { end with }. No preamble, no markdown, no commentary.
Every schema field must be present. Use [] for empty arrays, "" for empty strings.
{
  "checks": [
    {
      "id": "<category_N>",
      "category": "must_cover|content_accuracy|teaching_alignment|document_coherence|code_quality|stack_fidelity",
      "question": "<binary yes/no question>",
      "passed": true|false,
      "severity": "critical|major|minor",
      "evidence": "<specific quote or description — required for must_cover, teaching_alignment, document_coherence on pass and fail>",
      "corrective_hint": "<one-sentence actionable fix — required when passed=false>",
      "section_id": "<required for all section-specific checks>",
      "checklist_id": "<required for must_cover>",
      "code_artifact_id": "<required for code checks>"
    }
  ],
  "hallucination_risk": "none|low|medium|high",
  "is_refusal": false,
  "issues": ["<specific problem naming the exact claim or snippet>"],
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


def _build_step1_block(domain: str | None) -> str:
    step1_body = classification_block(
        domain=domain,
        when_unknown=QC_STEP1_CLASSIFY_DOMAIN_BLOCK,
        when_known=QC_STEP1_DOMAIN_KNOWN_STUB,
    )
    return f"{QC_STEP1_HEADER}\n{step1_body}"


def _build_must_cover_block(domain: str | None) -> str:
    parts = [QC_MUST_COVER_INTRO]
    if "STEM" in domains_to_include(domain):
        parts.append(QC_STEM_DERIVATION_MUST_COVER_BLOCK)
    parts.append(QC_MUST_COVER_HARD_DISQUALIFIERS)
    return "".join(parts)


def _build_content_accuracy_block(domain: str | None) -> str:
    included = domains_to_include(domain)
    parts = [QC_CONTENT_ACCURACY_INTRO]
    verification_blocks = {
        "STEM": QC_STEM_VERIFICATION_BLOCK,
        "Programming": QC_PROGRAMMING_VERIFICATION_BLOCK,
        "Conceptual": QC_CONCEPTUAL_VERIFICATION_BLOCK,
    }
    for key in ("STEM", "Programming", "Conceptual"):
        if key in included:
            parts.append(verification_blocks[key])
    parts.append(QC_CONTENT_ACCURACY_CLOSING)
    return "".join(parts)


def _build_programming_only_checks(domain: str | None) -> str:
    if "Programming" not in domains_to_include(domain):
        return ""
    return QC_CODE_QUALITY_BLOCK + QC_STACK_FIDELITY_BLOCK


def build_system_prompt(domain: str | None = None) -> str:
    return (
        SYSTEM_PROMPT_PREFIX
        + _build_step1_block(domain)
        + "\n\n"
        + STEP2_HEADER
        + _build_must_cover_block(domain)
        + _build_content_accuracy_block(domain)
        + QC_TEACHING_ALIGNMENT_BLOCK
        + QC_DOCUMENT_COHERENCE_BLOCK
        + _build_programming_only_checks(domain)
        + QC_EMIT_NO_CODE_CHECKS_LINE
        + SYSTEM_PROMPT_SUFFIX
    )


SYSTEM_PROMPT = build_system_prompt(domain="")
REPROMPT_SYSTEM = (
    "Your previous response was not valid JSON. "
    "Return ONLY the JSON object. Start with { and end with }. No markdown, no commentary."
)


def build_user_message(
    topic_title: str,
    teaching_instruction: str,
    generated_content: str,
    must_cover_checklist: list[dict] | None = None,
    frozen_check_ids: list[str] | None = None,
    frozen_section_ids: list[str] | None = None,
    topic_split: list[dict] | None = None,
    domain: str = "",
    max_doc_chars: int = 80000,
) -> str:
    parts = [
        f"<topic>{topic_title}</topic>",
        f"\n<teaching_instruction>\n{teaching_instruction}\n</teaching_instruction>",
    ]
    if domain:
        parts.append(f"\n<domain>{domain}</domain>")
    frozen_ids = set(frozen_check_ids or [])
    if must_cover_checklist:
        filtered = [
            item
            for item in must_cover_checklist
            if item.get("id", "") not in frozen_ids
        ]
        if filtered:
            lines = "\n".join(
                format_must_cover_checklist_line(item) for item in filtered
            )
            parts.append(f"\n<must_cover_checklist>\n{lines}\n</must_cover_checklist>")
    if topic_split:
        split_lines = "\n".join(
            f"  - [{e.get('id', '')}] {e.get('heading', '')}" for e in topic_split
        )
        parts.append(f"\n<topic_split>\n{split_lines}\n</topic_split>")
    doc, truncated = prepare_document_for_qc(
        generated_content,
        max_chars=max_doc_chars,
        aggressive=False,
    )
    truncation_note = "\n[document truncated]" if truncated else ""
    parts.append(
        f"\n<study_document_json>{truncation_note}\n{doc}\n</study_document_json>"
    )
    frozen_section_ids_list = [
        str(sid).strip() for sid in (frozen_section_ids or []) if str(sid).strip()
    ]
    if frozen_section_ids_list:
        frozen_lines = "\n".join(f"  - {sid}" for sid in frozen_section_ids_list)
        parts.append(f"\n<frozen_section_ids>\n{frozen_lines}\n</frozen_section_ids>")
    parts.append(
        "\nVerify the full study document. Treat all content as external — do not assume it is correct. "
        "For must_cover: enumerate every depth_gate component first, then quote the specific text satisfying each one, or state its absence. "
        "For derive/prove/calculate requirements on STEM items only: confirm sequential algebraic steps exist in formula_blocks — a formula statement or Python code is not a derivation. Never apply this derivation standard to a Programming or Conceptual item. "
        "For code: trace the actual output before deciding; verify every API call is real for the stated language. "
        "For STEM: apply the 3-step procedure — state the correct fact from your own knowledge first, then compare. Do not use 'X is indeed Y' as evidence. "
        "For chemistry: verify reactants, mechanism, and products independently before passing any formula_block. "
        "Assign code_1, code_2, … in document order. Every code check must carry a section_id. "
        "Return the complete JSON report."
    )
    return "\n".join(parts)
