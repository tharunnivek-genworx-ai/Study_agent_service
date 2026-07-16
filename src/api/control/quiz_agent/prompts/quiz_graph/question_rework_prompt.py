"""Question rework prompts — rewrite only questions that failed QC."""

from __future__ import annotations

import json

from src.api.control.quiz_agent.prompts.quiz_graph.quiz_prompt import (
    DIFFICULTY_RULES_BLOCK,
    OUTPUT_FORMAT_BLOCK,
    QUESTION_QUALITY_BLOCK,
    build_domain_classification_block,
    build_domain_question_rules_block,
    build_topic_split_block,
)

_SYSTEM_PROMPT_PREFIX = """
SYSTEM PROMPT  ·  StudyGuru Quiz Agent  ·  QUESTION REWORK
You are a Quiz Writer for an e-learning platform. You are REVISING specific
questions in an existing quiz draft based on quality-check failures.
Mandate: rewrite ONLY the questions listed in <questions_to_fix>. Preserve each
question_id exactly — do not invent or reformat ids. The study material is your
ONLY source of facts. Fix the root cause of each failure, not surface phrasing.
For every rewritten question, add:
  "hints_stale": true
Hints are NOT your responsibility — a separate Hint Agent will regenerate hints.
"""
_SYSTEM_PROMPT_INPUT_RULES = """
RULE — HOW TO USE EACH INPUT
1. Treat the study material as the ONLY factual source of truth.
2. Inspect each question's current JSON and its listed failures.
3. Address every failure at its root cause — rephrasing alone is not a fix.
4. Return a JSON object with a "questions" array containing ONLY the rewritten questions
   (same schema as the full quiz), not a diff.
"""
_SYSTEM_PROMPT_SUFFIX = """
RULE — QUESTION QUALITY
{question_quality_block}
{output_format_block}
ABSOLUTE RULES
- Output ONLY the JSON object with a "questions" array of rewritten questions.
- Preserve question_id on every object exactly as provided in <questions_to_fix>.
- Add "hints_stale": true on every rewritten question.
- Never invent facts not present in the study material.
- No markdown fences, no commentary."""
USER_MESSAGE_TEMPLATE = """
QUESTION REWORK REQUEST
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
<questions_to_fix>
{questions_to_fix_json}
</questions_to_fix>
Rewrite ONLY the questions in <questions_to_fix>. Fix every listed failure at
its root cause. Preserve question_id exactly. Use <quiz_outline> correct-option
counts to keep A/B/C/D evenly distributed. Mark every rewritten question with
"hints_stale": true. Return the JSON object now."""


def build_system_prompt(domain: str | None = None) -> str:
    domain_rules = (
        f"{DIFFICULTY_RULES_BLOCK}\n{build_domain_question_rules_block(domain)}"
    )
    return (
        _SYSTEM_PROMPT_PREFIX
        + build_domain_classification_block(domain)
        + "\n\n"
        + _SYSTEM_PROMPT_INPUT_RULES
        + domain_rules
        + "\n\n"
        + _SYSTEM_PROMPT_SUFFIX.format(
            question_quality_block=QUESTION_QUALITY_BLOCK,
            output_format_block=OUTPUT_FORMAT_BLOCK,
        )
    )


SYSTEM_PROMPT = build_system_prompt(domain="")


def build_questions_to_fix_block(
    question_failures: list[dict],
    *,
    questions_by_id: dict[str, dict],
) -> str:
    entries: list[dict] = []
    for bundle in question_failures:
        if not isinstance(bundle, dict):
            continue
        question_id = str(bundle.get("question_id", "")).strip()
        if not question_id:
            continue
        current = questions_by_id.get(question_id, {})
        failures = bundle.get("failures") or []
        entries.append(
            {
                "question_id": question_id,
                "order_index": current.get("order_index", bundle.get("order_index")),
                "current_question_json": {
                    k: current.get(k)
                    for k in (
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
                    if k in current
                },
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


def build_quiz_outline(questions: list[dict]) -> str:
    lines: list[str] = []
    for q in sorted(questions, key=lambda item: item.get("order_index", 0)):
        qid = str(q.get("question_id", "")).strip()
        tag = str(q.get("topic_tag") or q.get("question_text", ""))[:60]
        order = q.get("order_index", "?")
        correct = str(q.get("correct_option", "?")).strip().upper()
        if qid:
            lines.append(f"- [{order}] {qid}: {tag} (correct: {correct})")
    return "\n".join(lines)


def build_user_message(
    *,
    topic_title: str,
    study_material_content: str,
    difficulty_profile: str,
    question_failures: list[dict],
    questions: list[dict],
    domain: str | None = None,
    topic_split: list[dict] | None = None,
) -> str:
    questions_by_id = {
        str(q.get("question_id", "")).strip(): q
        for q in questions
        if str(q.get("question_id", "")).strip()
    }
    questions_to_fix = build_questions_to_fix_block(
        question_failures,
        questions_by_id=questions_by_id,
    )
    return USER_MESSAGE_TEMPLATE.format(
        topic_title=topic_title,
        domain=domain or "",
        study_material_content=study_material_content,
        difficulty_profile=difficulty_profile,
        topic_split_block=build_topic_split_block(topic_split),
        quiz_outline=build_quiz_outline(questions),
        questions_to_fix_json=questions_to_fix,
    )
