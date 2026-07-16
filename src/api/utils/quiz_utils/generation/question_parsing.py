"""Parse and normalize quiz question payloads from LLM responses."""

from __future__ import annotations

import json
import logging
import re
from typing import Any
from uuid import uuid4

logger = logging.getLogger(__name__)


def _strip_json_fences(raw: str) -> str:
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text
        if text.endswith("```"):
            text = text[: -len("```")]
        text = text.strip()
        if text.lower().startswith("json"):
            text = text[len("json") :].strip()
    return text


def _extract_question_items(parsed: Any) -> list:
    if isinstance(parsed, list):
        return parsed
    if isinstance(parsed, dict):
        questions = parsed.get("questions")
        if isinstance(questions, list):
            return questions
        raise ValueError("Expected JSON object with a 'questions' array.")
    raise ValueError("Expected a JSON array or object with 'questions'.")


def _countable_questions(items: list[Any]) -> list[dict[str, Any]]:
    return [
        item
        for item in items
        if isinstance(item, dict)
        and not str(item.get("question_text", "")).startswith("GENERATION NOTE")
    ]


def parse_json_array(raw: str, *, expected_count: int | None = None) -> list:
    """Parse quiz LLM output into a question list.

    Accepts either ``{"questions": [...]}`` (preferred) or a bare JSON array for
    backward compatibility. Tolerates accidental ```json fences around the payload.

    When ``expected_count`` is set, excess questions are trimmed. Under-count is
    returned as-is so deterministic validation can retry generation with feedback
    instead of aborting as a hard parse failure.
    """
    text = _strip_json_fences(raw)
    parsed = json.loads(text)
    items = _extract_question_items(parsed)
    if expected_count is not None:
        countable = _countable_questions(items)
        if len(countable) > expected_count:
            logger.warning(
                "Quiz output returned %d questions; trimming to expected %d.",
                len(countable),
                expected_count,
            )
            return countable[:expected_count]
        if len(countable) < expected_count:
            logger.warning(
                "Quiz output returned %d questions; expected %d "
                "(will retry via structural validation).",
                len(countable),
                expected_count,
            )
        return countable
    return items


def empty_to_none(value: Any) -> Any:
    if isinstance(value, str) and value.strip() == "":
        return None
    return value


def normalize_question_markdown(text: str) -> str:
    """Rewrite inline code fences to block fences for consistent markdown rendering."""
    if not text:
        return text

    normalized = text
    normalized = re.sub(r":[ \t]*```(\w*)(?=\n)", r"\n\n```\1", normalized)
    normalized = re.sub(r"([^\n`])```(?=\n|$)", r"\1\n```", normalized)
    return normalized


def normalize_parsed_items(
    items: list[Any],
) -> tuple[list[dict[str, Any]], list[str]]:
    parsed: list[dict[str, Any]] = []
    hints_stale_ids: list[str] = []
    order_index = 0
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("Quiz output element is not an object.")

        question_text = item.get("question_text")
        if isinstance(question_text, str) and question_text.startswith(
            "GENERATION NOTE"
        ):
            continue

        if isinstance(question_text, str):
            question_text = normalize_question_markdown(question_text)

        for field in (
            "question_text",
            "option_a",
            "option_b",
            "option_c",
            "option_d",
            "correct_option",
            "explanation",
        ):
            if item.get(field) in (None, ""):
                raise ValueError(f"Quiz question missing required field: {field}.")

        question_id = item.get("question_id") or str(uuid4())
        if item.get("hints_stale") is True:
            hints_stale_ids.append(str(question_id))

        parsed.append(
            {
                "question_id": question_id,
                "question_text": question_text,
                "option_a": item.get("option_a"),
                "option_b": item.get("option_b"),
                "option_c": empty_to_none(item.get("option_c")),
                "option_d": empty_to_none(item.get("option_d")),
                "correct_option": item.get("correct_option"),
                "explanation": item.get("explanation"),
                "difficulty": item.get("difficulty"),
                "domain": item.get("domain"),
                "topic_tag": item.get("topic_tag"),
                "order_index": order_index,
            }
        )
        order_index += 1

    return parsed, hints_stale_ids


def questions_for_qc(questions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    payload: list[dict[str, Any]] = []
    for q in questions:
        payload.append(
            {
                "question_id": str(q.get("question_id")),
                "question_text": q["question_text"],
                "option_a": q["option_a"],
                "option_b": q["option_b"],
                "option_c": q.get("option_c"),
                "option_d": q.get("option_d"),
                "correct_option": q["correct_option"],
                "explanation": q.get("explanation"),
                "difficulty": q.get("difficulty"),
                "domain": q.get("domain"),
                "topic_tag": q.get("topic_tag"),
                "order_index": q.get("order_index"),
            }
        )
    return payload
