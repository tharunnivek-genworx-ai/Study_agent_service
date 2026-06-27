"""Question insert prompts — write new questions for missing concepts only."""

from __future__ import annotations

import json

from src.api.control.quiz_agent.prompts.quiz_prompt import (
    DIFFICULTY_RULES_BLOCK,
    OUTPUT_FORMAT_BLOCK,
    QUESTION_QUALITY_BLOCK,
    build_domain_classification_block,
    build_domain_question_rules_block,
    build_topic_split_block,
)

_SYSTEM_PROMPT_PREFIX = """
SYSTEM PROMPT  ·  StudyGuru Quiz Agent  ·  QUESTION INSERT
You are a Quiz Writer for an e-learning platform. You are writing NEW quiz
questions for concepts that the current quiz does not cover.
Mandate: write ONLY questions for concepts listed in <missing_concepts>. Do not
duplicate concepts already covered in <existing_quiz_outline>. Match the
requested difficulty profile.
This is a FIRST GENERATION task scoped to missing concepts only. Hints are NOT
your responsibility.
RULE — SOURCE OF TRUTH
The study material provided is your ONLY source of facts. Every question, every
option, and every explanation must be answerable using only the study material.
"""
_SYSTEM_PROMPT_COVERAGE = """
RULE — COVERAGE
Write one strong question per missing concept unless the concept list specifies
otherwise. Do not repeat concepts already present in <existing_quiz_outline>.
"""
_SYSTEM_PROMPT_SUFFIX = """
RULE — QUESTION QUALITY
{question_quality_block}
{output_format_block}
ABSOLUTE RULES
- Output ONLY the JSON array of new question objects.
- Do NOT include question_id — the application assigns ids on merge.
- Produce exactly as many questions as there are missing concepts unless a
  concept genuinely cannot support a question (note in topic_tag).
- No markdown fences, no commentary."""
USER_MESSAGE_TEMPLATE = """
QUESTION INSERT REQUEST
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
<existing_quiz_outline>
{existing_quiz_outline}
</existing_quiz_outline>
<missing_concepts>
{missing_concepts_json}
</missing_concepts>
Write new questions for every concept in <missing_concepts>. Do not duplicate
concepts in <existing_quiz_outline>. Use <existing_quiz_outline> correct-option
counts to assign underrepresented letters (A/B/C/D). Return the JSON array now."""


def build_system_prompt(domain: str | None = None) -> str:
    domain_rules = (
        f"{DIFFICULTY_RULES_BLOCK}\n{build_domain_question_rules_block(domain)}"
    )
    return (
        _SYSTEM_PROMPT_PREFIX
        + build_domain_classification_block(domain)
        + "\n\n"
        + _SYSTEM_PROMPT_COVERAGE
        + domain_rules
        + "\n\n"
        + _SYSTEM_PROMPT_SUFFIX.format(
            question_quality_block=QUESTION_QUALITY_BLOCK,
            output_format_block=OUTPUT_FORMAT_BLOCK,
        )
    )


SYSTEM_PROMPT = build_system_prompt(domain="")


def build_user_message(
    *,
    topic_title: str,
    study_material_content: str,
    difficulty_profile: str,
    missing_concepts: list[str],
    existing_questions: list[dict],
    domain: str | None = None,
    topic_split: list[dict] | None = None,
) -> str:
    from src.api.control.quiz_agent.prompts.question_rework_prompt import (
        build_quiz_outline,
    )

    return USER_MESSAGE_TEMPLATE.format(
        topic_title=topic_title,
        domain=domain or "",
        study_material_content=study_material_content,
        difficulty_profile=difficulty_profile,
        topic_split_block=build_topic_split_block(topic_split),
        existing_quiz_outline=build_quiz_outline(existing_questions),
        missing_concepts_json=json.dumps(missing_concepts, ensure_ascii=False),
    )
