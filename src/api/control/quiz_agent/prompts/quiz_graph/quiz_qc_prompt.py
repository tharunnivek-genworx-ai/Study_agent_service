"""Quality check prompt for MCQ quiz evaluation."""

from __future__ import annotations

import json

from src.api.control.quiz_agent.prompts.quiz_graph.quiz_qc_check_definitions import (
    ANTI_INFLATION_RULES_BLOCK,
    JSON_OUTPUT_RULES_BLOCK,
    PER_QUESTION_CHECK_CATEGORIES_BLOCK,
    QC_OUTPUT_FORMAT_BLOCK,
    QUIZ_SUMMARY_BLOCK,
    RETRY_RECOMMENDATION_BLOCK,
    WRONG_ANSWER_RISK_BLOCK,
)
from src.api.utils.prompt_utils.domain_merge import classification_block

SYSTEM_PROMPT_PREFIX = """
SYSTEM PROMPT  ·  StudyGuru Quiz Quality Check Agent
You are a strict MCQ Quiz Evaluator for an e-learning platform. Treat every
question as coming from an external source you did not write. DEFAULT VERDICT:
every check starts as FAIL — a dimension passes ONLY when you can independently
confirm the specific claim is actually true, not merely present or well-worded.
You do NOT rewrite, fix, or regenerate any question. You only evaluate and report.
Inputs: topic, study material (source of truth), requested difficulty, and the
full quiz with all options, correct_option, explanation, and domain per question.
Structural checks (option count, blank fields) are already
verified in code — do NOT re-check those.
"""
QC_STEP1_HEADER = """
STEP 1 — CLASSIFY DOMAIN
"""
QC_STEP1_CLASSIFY_DOMAIN_BLOCK = """Read <topic> and <domain> if provided; otherwise classify from the study material:
  STEM         — equations, derivations, empirical values (math, physics, chemistry, …).
  Programming  — code, APIs, frameworks; correctness depends on syntax and runtime.
  Conceptual   — named facts and reasoning (history, law, business, social science, …).
  Mixed        — spans more than one; classify each question by what it actually tests."""
QC_STEP1_DOMAIN_KNOWN_STUB = "`<domain>` is authoritative; do not reclassify."
SYSTEM_PROMPT_SUFFIX = f"""
STEP 2 — PRODUCE ONE question_result PER QUESTION
{PER_QUESTION_CHECK_CATEGORIES_BLOCK}
STEP 3 — PRODUCE quiz_summary (once, for the whole quiz)
{QUIZ_SUMMARY_BLOCK}
{ANTI_INFLATION_RULES_BLOCK}
{WRONG_ANSWER_RISK_BLOCK}
{RETRY_RECOMMENDATION_BLOCK}
{JSON_OUTPUT_RULES_BLOCK}
{QC_OUTPUT_FORMAT_BLOCK}"""


def _build_step1_block(domain: str | None) -> str:
    step1_body = classification_block(
        domain=domain,
        when_unknown=QC_STEP1_CLASSIFY_DOMAIN_BLOCK,
        when_known=QC_STEP1_DOMAIN_KNOWN_STUB,
    )
    return f"{QC_STEP1_HEADER}\n{step1_body}"


def build_system_prompt(domain: str | None = None) -> str:
    return (
        SYSTEM_PROMPT_PREFIX
        + _build_step1_block(domain)
        + "\n\n"
        + SYSTEM_PROMPT_SUFFIX
    )


SYSTEM_PROMPT = build_system_prompt(domain="")
USER_MESSAGE_TEMPLATE = """
QUIZ QUALITY CHECK REQUEST
<topic>
{topic_title}
</topic>
<domain>
{domain}
</domain>
<requested_difficulty>
{difficulty}
</requested_difficulty>
<total_questions_requested>
{question_count}
</total_questions_requested>
<generation_mode>
{generation_mode}
</generation_mode>
<study_material>
{study_material_content}
</study_material>
<quiz_questions>
{quiz_questions_json}
</quiz_questions>
Evaluate every question against the study material and topic above.
For each question emit exactly one question_result object containing
answer_correctness_passed, answer_evidence, quality_passed, quality_evidence,
and corrective_hint.
question_results must contain exactly {question_count} objects — one per question.
Fill quiz_summary once for the whole quiz.
question_id values must exactly match quiz_questions input.
Return ONLY the complete JSON object described in OUTPUT CONTRACT.
"""


def build_user_message(
    *,
    topic_title: str,
    difficulty: str,
    question_count: int,
    generation_mode: str,
    study_material_content: str,
    quiz_questions: list[dict],
    domain: str | None = None,
    frozen_question_ids: list[str] | None = None,
) -> str:
    frozen_block = ""
    frozen_ids = [
        str(question_id).strip()
        for question_id in (frozen_question_ids or [])
        if str(question_id).strip()
    ]
    if frozen_ids:
        frozen_lines = "\n".join(f"  - {question_id}" for question_id in frozen_ids)
        frozen_block = (
            f"\n<frozen_question_ids>\n{frozen_lines}\n</frozen_question_ids>\n"
            "Do NOT re-evaluate questions listed in frozen_question_ids — "
            "they already passed QC on a prior attempt.\n"
        )

    return (
        USER_MESSAGE_TEMPLATE.format(
            topic_title=topic_title,
            domain=domain or "",
            difficulty=difficulty,
            question_count=question_count,
            generation_mode=generation_mode,
            study_material_content=study_material_content,
            quiz_questions_json=json.dumps(
                quiz_questions, ensure_ascii=False, default=str
            ),
        )
        + frozen_block
    )
