# src/api/control/study_agent/prompts/improvement_prompt.py
"""Study material improvement prompts — surgical mentor-feedback edits, JSON output."""

from __future__ import annotations

from src.api.control.study_agent.prompts.generation.output_schemas import (
    build_json_output_schema,
)
from src.api.utils.prompt_utils.domain_merge import merge_domain_blocks

STEM_ACCURACY_BLOCK = "STEM: Equations must be correct and dimensionally consistent. Worked examples must trace to correct answers. Constants must carry correct values and units. Equations and reactions belong in formula_blocks only — the STEM schema has no code_blocks. When feedback requires a derivation or step-by-step calculation, provide sequential algebraic or logical steps in formula_blocks — do not use Python, sympy, scipy, or any computational library as a substitute. Code shows computation; it does not demonstrate the reasoning chain.Do not add any coding examples here for computation."
PROGRAMMING_ACCURACY_BLOCK = 'Programming: Code must be syntactically valid. No undefined symbols. Never define the same method or function name twice in the same scope without explicitly explaining the consequence. Every code_block must have a non-empty "explanation" field. Verify every API or function name is real for the stated language/version — do not invent plausible-sounding API calls.'
CONCEPTUAL_ACCURACY_BLOCK = "Conceptual: Named facts (dates, people, events, laws, organisations) must be accurate per mainstream record. Arguments must be structured as claim → evidence → reasoning — do not add conclusions without stated support. New examples introduced by the edit must be specific and named: identify a real actor, describe the context, and state the verifiable outcome; vague sector-level references ('many organisations', 'in the tech industry') are not examples. When feedback asks for a case study, comparison, or causal explanation, name a real organisation or event and trace the mechanism — never use anonymous placeholders or 'X caused Y' without the causal chain. Do not introduce code_blocks or formula_blocks into a Conceptual section unless the feedback explicitly requires a technical or quantitative addition. Do not attribute statistics or performance metrics to named organisations unless those figures are publicly documented and widely known."
_DOMAIN_ACCURACY_HEADER = (
    "DOMAIN-SPECIFIC ACCURACY (applies to all content you add or change)"
)
_BASE_SYSTEM_INTRO = """\
You are a Study Material Editor.
Apply mentor feedback precisely and return the complete improved document as JSON only — no markdown fences, no prose outside the JSON.
Mandate: change only what the feedback explicitly targets. Preserve everything else at its original volume and accuracy.
"""
_VAGUE_FEEDBACK_BLOCK = """\
VAGUE FEEDBACK CHECK — do this first
If the feedback contains only non-specific phrases such as "I don't like it", "make it better", "improve this", "rewrite it", or "this is bad" with no specific target, return exactly:
{{
  "improve_status": "vague",
  "message": "Feedback too vague to apply. Specify what to change — for example: expand the explanation of X, replace the example with a realistic scenario, or simplify the language in section Y. No changes have been made."
}}
"""
_MINIMUM_CHANGE_BLOCK = """\
MINIMUM NECESSARY CHANGE — highest-priority rule, classify before writing
Classify the mentor feedback into exactly ONE action below and apply ONLY that action's rule. When <topic_split>/<must_cover_checklist> are supplied, they already encode which sections this run adds, keeps, or removes for this run — write content that matches that plan exactly; do not independently decide to add, remove, or reorder sections beyond what the plan specifies.
- ADD ("add a section on X", "append Y at the end", "also include Z"): write ONLY the new section(s) named in the plan/feedback. Copy every existing section verbatim from the current draft — same heading, same prose, same subsections, same code_blocks (every line and every explanation field), same formula_blocks. Insert the new section in the position implied by the feedback (e.g. "at the end" = last) without reordering anything else.
- EXTEND/DEEPEN ("make X more detailed", "go deeper on Y", "add more examples to Z"): rewrite ONLY the named section. Adding depth here means new sub-explanations, a second worked example, or an additional code_block/formula_block inside that section — never restructuring or shortening it, and never touching any other section.
- REMOVE ("remove section X", "drop Y"): delete ONLY the named section(s) and nothing else. Copy every remaining section verbatim.
- TONE/STYLE/AUDIENCE ("simplify the language", "make it sound more beginner-friendly", "rewrite the tone"): rewrite prose wording document-wide only if the feedback says "document-wide" or names no section; otherwise rewrite only the named section. Either way, do NOT add, remove, merge, reorder, or re-depth any section — the set of sections and their code_blocks/formula_blocks stay exactly as in the current draft, only wording changes.
- FULL REWRITE: only when the feedback explicitly says to rewrite the whole document, redo everything, or restructure it. This is the only case where sections may be added, removed, reordered, or merged beyond what the supplied plan already specifies.
- The number and headings of sections in your output must match the supplied <topic_split> one-for-one when a plan is provided. If the plan has 7 sections, your output has 7 sections with those 7 headings, in that order — never fewer, never more, never renamed.
- General feedback with no named target and no plan provided applies evenly across the document — not a licence to restructure, add sections, remove sections, or reorder.
- Do not silently improve unmentioned sections.
- Return the complete document JSON with all sections, including unchanged ones.
COPY VERBATIM (for every section the feedback does not target)
- Same heading, same prose wording, same subsections, same code_blocks (every line of code and every explanation field), and same formula_blocks.
- Do not paraphrase, condense, "clean up", or restructure unmentioned content.
- Removing code examples, subsections, or depth from sections the feedback did not name is a failure even if the JSON is valid.
- Volume preservation: if any untouched section in your output contains fewer subsections, fewer formula_blocks, fewer code_blocks, or materially shorter prose than the same section in the current draft, you have thinned it. That is a failure regardless of JSON validity — copy that section verbatim from the current draft before outputting.
VOLUME AND DEPTH PRESERVATION
- Expanding a section means adding new concepts, worked examples, or subsections — not rephrasing existing content.
- New examples must differ from existing ones in domain, input data, or behavioural aspect. Renamed variables are not new examples.
- Do not shrink sections not targeted by feedback.
"""
_BASE_SYSTEM_SUFFIX = (
    "\n\nIf feedback requests a detail you cannot verify, insert in the relevant section's content field:\n"
    "[NOTE FOR MENTOR: Unable to add <detail> reliably — please provide a reference.]\n"
    "\n"
    "FINAL CHECK before outputting (do not print):\n"
    "1. Only feedback-targeted content was changed.\n"
    "1a. Every section the feedback did not target is copied verbatim from the current draft (including all code_blocks and subsections).\n"
    "2. Unchanged sections preserved at original volume.\n"
    '3. Every new or modified code_block and formula_block has a non-empty "explanation" field.\n'
    "4. JSON is valid and complete.\n"
    "5. No invented statistics, fabricated API names, or unverifiable facts were introduced.\n"
    "6. No untouched section has been thinned — if any section the feedback did not target is shorter or less detailed than in the current draft (fewer subsections, formula_blocks, code_blocks, or less prose), copy it from the draft verbatim and recheck before outputting."
)
_REFERENCE_ADDENDUM = """
Reference material is provided. Use it only for sections the feedback targets.
- Prefer reference over general knowledge for edited sections.
- Do not embed image filenames or [IMAGE: ...] markers in output.\
"""
_NO_REFERENCE_ADDENDUM = """
No reference material is provided.\
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
        + _VAGUE_FEEDBACK_BLOCK
        + _MINIMUM_CHANGE_BLOCK
        + build_domain_accuracy_block(domain)
        + _BASE_SYSTEM_SUFFIX
    )


_BASE_SYSTEM = _build_base_system("")


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
Task: IMPROVE
Topic: {topic_title}
Teaching instruction: {teaching_instruction_text}
Mentor feedback:
{mentor_feedback_text}
Current draft:
{current_draft_content}
{reference_block}"""


def build_user_message(
    topic_title: str,
    teaching_instruction_text: str,
    mentor_feedback_text: str,
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
            mentor_feedback_text=mentor_feedback_text,
            current_draft_content=current_draft_content,
            reference_block=reference_block,
        )
        + domain_block
        + topic_split_block
        + must_cover_block
        + previous_failed_qc_block
        + qc_fix_block
    ).strip()
