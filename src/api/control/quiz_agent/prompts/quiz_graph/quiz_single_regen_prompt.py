"""Quiz single-question regeneration prompts — revise specific quiz questions from mentor feedback.

Distinct from ``question_rework_prompt`` (internal QC failures). Mentors supply
free-form feedback; the model classifies minimum-change actions and returns only
the regenerated question objects with ``hints_stale: true``.
"""

from __future__ import annotations

import json

from src.api.control.quiz_agent.prompts.quiz_graph.question_rework_prompt import (
    build_quiz_outline,
)
from src.api.control.quiz_agent.prompts.quiz_graph.quiz_prompt import (
    DIFFICULTY_RULES_BLOCK,
    OUTPUT_FORMAT_BLOCK,
    QUESTION_QUALITY_BLOCK,
    build_domain_classification_block,
    build_domain_question_rules_block,
    build_topic_split_block,
)

_SYSTEM_PROMPT_PREFIX = """
SYSTEM PROMPT  ·  StudyGuru Quiz Agent  ·  MENTOR QUESTION REWORK
You are a Quiz Writer for an e-learning platform. You are REVISING specific
questions in an existing quiz draft based on a mentor's feedback.
Mandate: rewrite ONLY the questions listed in <questions_to_rework>. Preserve each
question_id exactly — do not invent or reformat ids. Do not touch questions that
are not listed. The study material is your ONLY source of facts.
For every rewritten question, add:
  "hints_stale": true
Hints are NOT your responsibility — a separate Hint Agent will regenerate hints.
"""
_VAGUE_FEEDBACK_GUARD = """
VAGUE FEEDBACK CHECK — do this first
If <mentor_feedback> contains only non-specific phrases such as "I don't like it",
"make it better", "improve this", "rewrite it", or "this is bad" with no specific
target (which question aspect to change, what is wrong, or what outcome is desired),
return exactly:
{
  "rework_status": "vague",
  "message": "Feedback too vague to apply. Specify what to change — for example: make the distractors more challenging, rewrite the stem to test application not recall, simplify the wording, or replace this question with one on topic X. No changes have been made."
}
"""
_ACTION_TAXONOMY_BLOCK = """
STEP 2 — CLASSIFY FEEDBACK INTO ONE MINIMUM-CHANGE ACTION
Read <mentor_feedback> and classify it into exactly ONE action below. Apply ONLY
that action's rule to each question in <questions_to_rework>. When feedback names
a specific question aspect, honour it over the default action.

ACTION 1 — REVISE WORDING
Feedback targets phrasing, clarity, tone, or explanation quality without changing
what concept is tested or which option is correct.
- Rewrite question_text and/or explanation only.
- Keep option_a..option_d and correct_option unchanged unless a distractor is
  factually wrong per the study material.
- Preserve difficulty, domain, and topic_tag unless feedback explicitly asks to
  change them.

ACTION 2 — REPLACE DISTRACTORS
Feedback says distractors are too easy, too similar, obviously wrong, or misleading
in the wrong way — but the stem and tested concept are fine.
- Keep question_text, correct_option, explanation, difficulty, domain, and
  topic_tag unless feedback says otherwise.
- Replace one or more wrong options with plausible misconceptions from the study
  material. Ensure correct_option still points to the factually correct option.

ACTION 3 — REPLACE WHOLE QUESTION
Feedback asks for a different question on the same concept, a new concept, or says
the question is weak, off-topic, redundant, or factually unsupported.
- Write a new MCQ that satisfies the feedback while staying grounded in the study
  material.
- Preserve question_id and order_index from the input.
- Rebalance correct_option using <quiz_outline> so A/B/C/D stay evenly distributed
  across the full quiz after your change.

ACTION 4 — ADJUST DIFFICULTY
Feedback asks to make the question easier or harder without replacing the concept.
- Change difficulty and adjust stem/options/explanation to match the new tier per
  <difficulty_profile> and domain rules.
- Keep the same core concept unless feedback also requests ACTION 3.

If feedback spans multiple actions, pick the single action that satisfies the
mentor's primary intent with the smallest change. Escalate to ACTION 3 only when
lighter actions cannot honour the feedback.
"""
_SYSTEM_PROMPT_INPUT_RULES = """
STEP 1 — HOW TO USE EACH INPUT
1. Treat <study_material> as the ONLY factual source of truth.
2. Read <quiz_outline> for distribution context — keep correct_option spread fair
   across the full quiz when you change correct_option.
3. Inspect each question's current JSON in <questions_to_rework>.
4. Apply <mentor_feedback> as the primary directive for what changes.
5. Return a JSON object with a "questions" array containing ONLY the reworked questions
   (same schema as the full quiz), not a diff. Every returned object must include
   question_id and "hints_stale": true.
"""
_SYSTEM_PROMPT_SUFFIX = """
RULE — QUESTION QUALITY
{question_quality_block}
{output_format_block}
OUTPUT EXTENSION — MENTOR REWORK
Each object in the returned "questions" array MUST also include:
  "question_id": "<preserve exactly from <questions_to_rework>>"
  "hints_stale": true
ABSOLUTE RULES
- Output ONLY the JSON object with a "questions" array of reworked questions, OR the
  vague-feedback object from VAGUE FEEDBACK CHECK when feedback is too vague.
- Preserve question_id on every reworked question exactly as provided.
- Add "hints_stale": true on every reworked question.
- Never invent facts not present in the study material.
- Do not return questions that were not listed in <questions_to_rework>.
- No markdown fences, no commentary."""
USER_MESSAGE_TEMPLATE = """
MENTOR QUESTION REWORK REQUEST
<topic>
{topic_title}
</topic>
<domain>
{domain}
</domain>
<study_material>
{study_material_content}
</study_material>
<difficulty_profile>
{difficulty_profile}
</difficulty_profile>
{topic_split_block}
<quiz_outline>
{quiz_outline}
</quiz_outline>
<questions_to_rework>
{questions_to_rework_json}
</questions_to_rework>
<mentor_feedback>
{mentor_feedback}
</mentor_feedback>
Rewrite ONLY the questions in <questions_to_rework> per <mentor_feedback>.
Preserve question_id exactly. Use <quiz_outline> correct-option counts to keep
A/B/C/D evenly distributed when you change correct_option. Mark every rewritten
question with "hints_stale": true. Return the JSON object now."""


def build_system_prompt(domain: str | None = None) -> str:
    domain_rules = (
        f"{DIFFICULTY_RULES_BLOCK}\n{build_domain_question_rules_block(domain)}"
    )
    return (
        _SYSTEM_PROMPT_PREFIX
        + _VAGUE_FEEDBACK_GUARD
        + build_domain_classification_block(domain)
        + "\n\n"
        + _SYSTEM_PROMPT_INPUT_RULES
        + _ACTION_TAXONOMY_BLOCK
        + domain_rules
        + "\n\n"
        + _SYSTEM_PROMPT_SUFFIX.format(
            question_quality_block=QUESTION_QUALITY_BLOCK,
            output_format_block=OUTPUT_FORMAT_BLOCK,
        )
    )


SYSTEM_PROMPT = build_system_prompt(domain="")


_QUESTION_JSON_KEYS = (
    "question_id",
    "question_text",
    "option_a",
    "option_b",
    "option_c",
    "option_d",
    "correct_option",
    "explanation",
    "difficulty",
    "domain",
    "topic_tag",
    "order_index",
)


def build_questions_to_rework_block(
    question_ids: list[str],
    *,
    questions_by_id: dict[str, dict],
) -> str:
    entries: list[dict] = []
    for raw_id in question_ids:
        question_id = str(raw_id).strip()
        if not question_id:
            continue
        current = questions_by_id.get(question_id, {})
        entries.append(
            {
                "question_id": question_id,
                "order_index": current.get("order_index"),
                "current_question_json": {
                    k: current.get(k) for k in _QUESTION_JSON_KEYS if k in current
                },
            }
        )
    return json.dumps(entries, indent=2, ensure_ascii=False)


def build_user_message(
    *,
    topic_title: str,
    study_material_content: str,
    difficulty_profile: str,
    mentor_feedback: str,
    question_ids: list[str],
    questions: list[dict],
    domain: str | None = None,
    topic_split: list[dict] | None = None,
) -> str:
    questions_by_id = {
        str(q.get("question_id", "")).strip(): q
        for q in questions
        if str(q.get("question_id", "")).strip()
    }
    questions_to_rework = build_questions_to_rework_block(
        question_ids,
        questions_by_id=questions_by_id,
    )
    return USER_MESSAGE_TEMPLATE.format(
        topic_title=topic_title,
        domain=domain or "",
        study_material_content=study_material_content,
        difficulty_profile=difficulty_profile,
        topic_split_block=build_topic_split_block(topic_split),
        quiz_outline=build_quiz_outline(questions),
        questions_to_rework_json=questions_to_rework,
        mentor_feedback=mentor_feedback.strip(),
    )


def build_quiz_single_regen_prompt(
    *,
    topic_title: str,
    study_material_content: str,
    difficulty_profile: str,
    mentor_feedback: str,
    question_ids: list[str],
    questions: list[dict],
    domain: str | None = None,
    topic_split: list[dict] | None = None,
) -> dict[str, str]:
    """Assemble system + user messages for a quiz single-question regen LLM call."""
    return {
        "system_prompt": build_system_prompt(domain=domain),
        "user_message": build_user_message(
            topic_title=topic_title,
            study_material_content=study_material_content,
            difficulty_profile=difficulty_profile,
            mentor_feedback=mentor_feedback,
            question_ids=question_ids,
            questions=questions,
            domain=domain,
            topic_split=topic_split,
        ),
    }
