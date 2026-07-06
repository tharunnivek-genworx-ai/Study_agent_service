# src/api/control/study_agent/prompts/regeneration_prompt.py
"""Study material regeneration prompts — purposeful rewrite based on a mentor goal."""

from __future__ import annotations

from src.api.control.study_agent.prompts.generation.output_schemas import (
    build_json_output_schema,
)
from src.api.utils.prompt_utils.domain_merge import merge_domain_blocks

STEM_ACCURACY_BLOCK = (
    "STEM: Equations must be correct and dimensionally consistent. Worked examples must trace to correct answers. "
    "Constants must carry correct values and units. Equations and reactions belong in formula_blocks only — this "
    "schema has no code_blocks field, for any STEM section, regardless of whether the feedback or checklist item "
    "uses derive/prove/calculate/apply/determine. Never use Python, sympy, scipy, or any computational library as "
    "a substitute for formula_block steps — code shows computation, it does not demonstrate the reasoning chain. "
    "Do not add coding examples for computation in a STEM section under any circumstances. "
    "A derive/prove/step-by-step section must contain at least 4 chained formula_block entries — a start, at "
    "least two distinct intermediate steps, and a final result; recompute every step from the one before it "
    "before finalizing, and delete any step that does not follow validly, even if the final answer is correct. "
    "Do not introduce a new or 'alternative' derivation method as part of a fix unless you can execute every one "
    "of its steps correctly — an unverified alternative method introduced during a fix is a new failure, not an "
    "improvement. If two sections in the document establish the same result, they must use genuinely different "
    "methods or examples, never the same construction restated."
)
PROGRAMMING_ACCURACY_BLOCK = 'Programming: Code must be syntactically valid and run correctly on the demonstrated path. Every symbol must be defined or imported in the same block. Never define the same method or function name twice in the same scope without explaining the consequence. Every code_block must have a non-empty "explanation" field. Verify every API or function name is real for the stated language/version.'
CONCEPTUAL_ACCURACY_BLOCK = "Conceptual: Named facts (dates, people, events, laws, organisations) must be accurate per mainstream record. Examples must be specific and named: identify a real actor, describe the context, and state the verifiable outcome — 'many organisations' or 'in the tech sector' without a named entity is not an example. Causal claims must reflect actual historical or empirical record, not merely plausible generalisations; when the regeneration goal demands causal analysis, trace precondition → trigger → mechanism → outcome explicitly. When the goal demands comparison: name both sides and provide a specific named case for each. Do not introduce code_blocks or formula_blocks into a Conceptual section unless the regeneration goal explicitly requires a technical or quantitative addition. Do not attribute statistics or performance metrics to named organisations unless those figures are publicly documented and widely known."
_DOMAIN_ACCURACY_HEADER = "DOMAIN-SPECIFIC ACCURACY (applies to everything you write)"
_BASE_SYSTEM_INTRO = """\
You are a Study Material Writer.
This is a REGENERATE task. Return ONLY a valid JSON object — no markdown fences, no prose outside the JSON.
Mandate: apply the regeneration goal with minimum necessary change. Do NOT rewrite the whole document unless the mentor explicitly asks for a full rewrite.
"""
_VAGUE_GOAL_BLOCK = """\
VAGUE GOAL CHECK — do this first
If the regeneration goal contains only non-specific phrases such as "redo this", "make it better", "rewrite it", or "this is bad", return exactly:
{{
  "regenerate_status": "vague",
  "message": "Regeneration goal too vague to apply. Describe the outcome you want — for example: rewrite from a beginner perspective, make the material more hands-on, or add more depth to how Y works. No changes have been made."
}}
"""
_SCOPE_BLOCK = """\
SCOPE — classify the goal before writing (highest-priority rule)
Classify the regeneration goal into exactly ONE action below and apply ONLY that action's rule. When <topic_split>/<must_cover_checklist> are supplied, they already encode which sections this run adds, keeps, or removes — write content that matches that plan exactly; do not independently decide to add, remove, or reorder sections beyond what the plan specifies.
- ADD (e.g. "add a section on X", "append Y at the end", "also include Z"): write ONLY the new section(s). Copy every existing section verbatim from the current draft — same headings, prose, subsections, code_blocks, and formula_blocks. Do not rephrase, shorten, merge, reorder, or remove anything in existing sections.
- MODIFY/DEEPEN ONE OR MORE NAMED SECTIONS (e.g. "expand section Y", "add a coding example for useEffect", "fix the example in Z"): rewrite ONLY the named section(s) — go deeper by adding sub-explanations, a second example, or an extra code_block/formula_block inside that section. Copy all other sections verbatim from the current draft.
- REMOVE (e.g. "remove section X"): delete ONLY the named section(s). Copy all other sections verbatim.
- TONE/LEVEL REWRITE WITH NO SECTION NAMED (e.g. "make this more beginner-friendly", "give it a more engaging voice"): rewrite prose wording throughout, but the set of sections, their order, and their headings stay exactly as in the current draft — this goal type never adds, removes, or reorders sections.
- FULL REWRITE: only when the goal explicitly targets the whole document, says "redo everything", or asks to restructure it. This is the only case where sections may be added, removed, reordered, or merged beyond what the supplied plan already specifies.
- The number and headings of sections in your output must match the supplied <topic_split> one-for-one when a plan is provided — never fewer, never more, never renamed, regardless of how "thorough" or "in depth" the goal asks the named section(s) to become.
COPY VERBATIM (for every section the goal does not target)
- Same heading, same prose wording, same subsections, same code_blocks (every line of code and every explanation field), and same formula_blocks.
- Do not paraphrase, condense, "clean up", or restructure unmentioned content.
- Removing code examples, subsections, or depth from sections the goal did not name is a failure even if the JSON is valid.
- "Make it detailed" or "in depth" applies ONLY to the section(s) the goal names — never as licence to rewrite other sections.
- Volume preservation: if any untouched section in your output contains fewer subsections, fewer formula_blocks, fewer code_blocks, or materially shorter prose than the same section in the current draft, you have thinned it. That is a failure regardless of JSON validity — copy that section verbatim from the current draft before outputting.
"""
_BASE_SYSTEM_SUFFIX = (
    "\n\nSUBSTANCE\n"
    "- Every section: definition + mechanism (how and why) + concrete example, written with genuine teaching depth rather than a brief summary.\n"
    "- When <must_cover_checklist> is present, every required item must satisfy its depth_gate — demonstrated, not just named.\n"
    "- In sections you rewrite: do not carry over inaccurate content from the draft.\n"
    "- In sections you do not rewrite: the current draft is authoritative — copy them verbatim.\n"
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
    "1. Regeneration goal is clearly addressed with minimum necessary change.\n"
    "1a. Every section the goal did not target is copied verbatim from the current draft (including all code_blocks and subsections).\n"
    "2. Every required checklist item satisfies its depth_gate.\n"
    '3. All code_blocks and formula_blocks have non-empty "explanation" fields.\n'
    "4. No code uses undefined symbols.\n"
    "5. All domain-specific accuracy rules are met.\n"
    "6. STEM sections requiring derivation contain sequential algebraic steps in formula_blocks — not Python code and not a formula statement with a one-sentence explanation.\n"
    "7. JSON is complete and valid.\n"
    "8. No untouched section has been thinned — if any section the goal did not target is shorter or less detailed than in the current draft (fewer subsections, formula_blocks, code_blocks, or less prose), copy it from the draft verbatim and recheck before outputting."
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
        _BASE_SYSTEM_INTRO
        + build_json_output_schema(domain)
        + "\n"
        + _VAGUE_GOAL_BLOCK
        + _SCOPE_BLOCK
        + build_domain_accuracy_block(domain)
        + _BASE_SYSTEM_SUFFIX
    )


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
Current draft (authoritative baseline — copy verbatim every section the goal does not target):
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
