"""Parse and normalize quiz question payloads from LLM responses."""

from __future__ import annotations

import json
import re
from typing import Any
from uuid import uuid4


def parse_json_array(raw: str) -> list:
    """Parse an LLM response that should be a JSON array.

    Tolerates accidental ```json fences around the payload.
    """
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text
        if text.endswith("```"):
            text = text[: -len("```")]
        text = text.strip()
        if text.lower().startswith("json"):
            text = text[len("json") :].strip()
    parsed = json.loads(text)
    if not isinstance(parsed, list):
        raise ValueError("Expected a JSON array.")
    return parsed


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
