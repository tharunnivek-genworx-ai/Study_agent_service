"""Targeted QC re-verification for revised or inserted quiz questions."""

from __future__ import annotations

import json

from src.api.control.quiz_agent.prompts.quiz_qc_check_definitions import (
    ANTI_INFLATION_RULES_BLOCK,
    JSON_OUTPUT_RULES_BLOCK,
    PER_QUESTION_CHECK_CATEGORIES_BLOCK,
    QC_OUTPUT_FORMAT_BLOCK,
    QUIZ_SUMMARY_BLOCK,
    RETRY_RECOMMENDATION_BLOCK,
    WRONG_ANSWER_RISK_BLOCK,
)

SYSTEM_PROMPT = f"""
SYSTEM PROMPT  ·  StudyGuru Quiz Quality Check Agent  ·  TARGETED RE-VERIFY
You are a strict MCQ Quiz Evaluator performing a TARGETED re-verification pass.
DEFAULT VERDICT: every dimension starts as FAIL.
Re-verify ONLY the questions in <revised_questions_json>. Re-evaluate quiz_summary
once against the full quiz in <full_quiz_questions>.
Structural checks are verified in code — do NOT re-check option count or
blank fields.
Before deciding any result for a revised question:
1. Read the prior failure description in <previously_failed> when present.
2. Read the revised question in <revised_questions_json>.
3. Ask: is the root cause of the prior failure actually fixed, or was only
   surface phrasing changed? Surface phrasing changes without fixing the root
   cause must still FAIL.
PRODUCE ONE question_result PER REVISED QUESTION
{PER_QUESTION_CHECK_CATEGORIES_BLOCK}
PRODUCE quiz_summary FOR THE FULL QUIZ
{QUIZ_SUMMARY_BLOCK}
{ANTI_INFLATION_RULES_BLOCK}
{WRONG_ANSWER_RISK_BLOCK}
{RETRY_RECOMMENDATION_BLOCK}
{JSON_OUTPUT_RULES_BLOCK}
{QC_OUTPUT_FORMAT_BLOCK}"""
USER_MESSAGE_TEMPLATE = """
QUIZ TARGETED QC RE-VERIFICATION
<topic>
{topic_title}
</topic>
<domain>
{domain}
</domain>
<requested_difficulty>
{difficulty}
</requested_difficulty>
<total_questions_in_quiz>
{question_count}
</total_questions_in_quiz>
<study_material>
{study_material_content}
</study_material>
<previously_failed>
{previously_failed_json}
</previously_failed>
<revised_questions_json>
{revised_questions_json}
</revised_questions_json>
<full_quiz_questions>
{full_quiz_questions_json}
</full_quiz_questions>
Evaluate only the {revised_count} revised question(s) above.
For each, emit one question_result with: {per_question_dimensions}.
question_results must contain exactly {revised_count} objects.
Update quiz_summary to reflect the full quiz in <full_quiz_questions>.
Return ONLY the complete JSON object described in OUTPUT CONTRACT.
"""


def build_previously_failed_block(question_failures: list[dict]) -> str:
    entries: list[dict] = []
    for bundle in question_failures:
        if not isinstance(bundle, dict):
            continue
        question_id = str(bundle.get("question_id", "")).strip()
        if not question_id:
            continue
        failures = bundle.get("failures") or []
        entries.append(
            {
                "question_id": question_id,
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
    return json.dumps(entries, indent=2, ensure_ascii=False)


def build_user_message(
    *,
    topic_title: str,
    difficulty: str,
    question_count: int,
    study_material_content: str,
    revised_questions: list[dict],
    full_quiz_questions: list[dict],
    question_failures: list[dict],
    domain: str | None = None,
) -> str:
    revised_count = len(revised_questions)
    return USER_MESSAGE_TEMPLATE.format(
        topic_title=topic_title,
        domain=domain or "",
        difficulty=difficulty,
        question_count=question_count,
        study_material_content=study_material_content,
        previously_failed_json=build_previously_failed_block(question_failures),
        revised_questions_json=json.dumps(
            revised_questions, ensure_ascii=False, default=str, indent=2
        ),
        full_quiz_questions_json=json.dumps(
            full_quiz_questions, ensure_ascii=False, default=str, indent=2
        ),
        per_question_dimensions="answer_correctness_passed + answer_evidence + quality_passed + quality_evidence + corrective_hint",
        revised_count=revised_count,
    )
