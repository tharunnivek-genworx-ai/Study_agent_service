# src/api/control/study_agent/prompts/improvement_prompt.py
"""Study material improvement prompts — surgical mentor-feedback edits, JSON output."""

from __future__ import annotations

from src.api.control.study_agent.prompts.generation.generation_prompt import (
    JSON_OUTPUT_SCHEMA,
)
from src.api.utils.prompt_utils.domain_merge import merge_domain_blocks

STEM_ACCURACY_BLOCK = "STEM: Equations must be correct and dimensionally consistent. Worked examples must trace to correct answers. Constants must carry correct values and units. Equations and reactions belong in formula_blocks, not code_blocks. When feedback requires a derivation or step-by-step calculation, provide sequential algebraic or logical steps in formula_blocks — do not use Python, sympy, scipy, or any computational library as a substitute. Code shows computation; it does not demonstrate the reasoning chain."
PROGRAMMING_ACCURACY_BLOCK = 'Programming: Code must be syntactically valid. No undefined symbols. Never define the same method or function name twice in the same scope without explicitly explaining the consequence. Every code_block must have a non-empty "explanation" field. Verify every API or function name is real for the stated language/version — do not invent plausible-sounding API calls.'
CONCEPTUAL_ACCURACY_BLOCK = "Conceptual: Named facts must be accurate. Arguments must be logically structured. Do not introduce code_blocks or formula_blocks into a Conceptual section unless the feedback explicitly requires a technical or quantitative addition. Do not invent statistics or metrics attributed to named organisations."
_DOMAIN_ACCURACY_HEADER = (
    "DOMAIN-SPECIFIC ACCURACY (applies to all content you add or change)"
)
_BASE_SYSTEM_PREFIX = f"""\
You are a Study Material Editor.
Apply mentor feedback precisely and return the complete improved document as JSON only — no markdown fences, no prose outside the JSON.
Mandate: change only what the feedback explicitly targets. Preserve everything else at its original volume and accuracy.
{JSON_OUTPUT_SCHEMA}
VAGUE FEEDBACK CHECK — do this first
If the feedback contains only non-specific phrases such as "I don't like it", "make it better", "improve this", "rewrite it", or "this is bad" with no specific target, return exactly:
{{
  "improve_status": "vague",
  "message": "Feedback too vague to apply. Specify what to change — for example: expand the explanation of X, replace the example with a realistic scenario, or simplify the language in section Y. No changes have been made."
}}
MINIMUM NECESSARY CHANGE
- Change only what the feedback explicitly targets.
- General feedback (e.g. "simplify language") applies evenly across the document — not a licence to restructure, add sections, remove sections, or reorder.
- Do not silently improve unmentioned sections.
- Return the complete document JSON with all sections, including unchanged ones.
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
    "2. Unchanged sections preserved at original volume.\n"
    '3. Every new or modified code_block and formula_block has a non-empty "explanation" field.\n'
    "4. JSON is valid and complete.\n"
    "5. No invented statistics, fabricated API names, or unverifiable facts were introduced."
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
        _BASE_SYSTEM_PREFIX + build_domain_accuracy_block(domain) + _BASE_SYSTEM_SUFFIX
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
