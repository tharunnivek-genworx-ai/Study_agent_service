"""Question prune prompts — remove surplus questions not aligned with study material."""

from __future__ import annotations

import json

from src.api.control.quiz_agent.prompts.quiz_graph.quiz_prompt import (
    build_domain_classification_block,
    build_topic_split_block,
)

_SYSTEM_PROMPT_PREFIX = """
SYSTEM PROMPT  ·  StudyGuru Quiz Agent  ·  QUESTION PRUNE
You are a Quiz Editor for an e-learning platform. The quiz draft has MORE
questions than the mentor requested. Your only job is to choose which
question(s) to REMOVE so the quiz matches the required count.
Mandate: remove questions that are least needed and least aligned with the
study material. Prefer removing questions that:
1. Are not answerable from the study material alone
2. Duplicate concepts already covered by stronger questions
3. Are the weakest fit for the topic split / requested difficulty
Keep the strongest, study-material-aligned questions.
"""
_SYSTEM_PROMPT_SUFFIX = """
ABSOLUTE RULES
- Output ONLY a JSON object with a "remove_question_ids" array of strings.
- Remove EXACTLY the number of questions specified in <remove_count>.
- Every id MUST appear in <existing_quiz_outline>.
- Do NOT rewrite questions. Do NOT invent new ids.
- No markdown fences, no commentary."""
USER_MESSAGE_TEMPLATE = """
QUESTION PRUNE REQUEST
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
<required_question_count>
{required_count}
</required_question_count>
<remove_count>
{remove_count}
</remove_count>
<existing_quiz_outline>
{existing_quiz_outline}
</existing_quiz_outline>
<existing_questions>
{existing_questions_json}
</existing_questions>
{extra_command_block}
The quiz currently has too many questions. Remove exactly {remove_count}
question(s) that are not needed or not aligned with the study material.
Return JSON: {{"remove_question_ids": ["..."]}} now."""


def build_system_prompt(domain: str | None = None) -> str:
    return (
        _SYSTEM_PROMPT_PREFIX
        + build_domain_classification_block(domain)
        + "\n\n"
        + _SYSTEM_PROMPT_SUFFIX
    )


SYSTEM_PROMPT = build_system_prompt(domain="")


def build_user_message(
    *,
    topic_title: str,
    study_material_content: str,
    difficulty_profile: str,
    required_count: int,
    remove_count: int,
    existing_questions: list[dict],
    domain: str | None = None,
    topic_split: list[dict] | None = None,
    extra_command: str | None = None,
) -> str:
    from src.api.control.quiz_agent.prompts.quiz_graph.question_rework_prompt import (
        build_quiz_outline,
    )

    command = (extra_command or "").strip()
    extra_command_block = (
        f"<prune_command>\n{command}\n</prune_command>\n" if command else ""
    )
    return USER_MESSAGE_TEMPLATE.format(
        topic_title=topic_title,
        domain=domain or "",
        study_material_content=study_material_content,
        difficulty_profile=difficulty_profile,
        topic_split_block=build_topic_split_block(topic_split),
        required_count=required_count,
        remove_count=remove_count,
        existing_quiz_outline=build_quiz_outline(existing_questions),
        existing_questions_json=json.dumps(existing_questions, ensure_ascii=False),
        extra_command_block=extra_command_block,
    )
