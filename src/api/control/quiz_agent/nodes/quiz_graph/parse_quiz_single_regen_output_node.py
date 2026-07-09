"""Parse LLM output for single-question mentor rework.

Graph node (rework subgraph)
----------------------------
Parses JSON patches or a ``rework_status: vague`` response when mentor feedback
is too ambiguous. Validates that returned ``question_id`` set matches request.

Outputs: ``parsed_patches`` or ``error`` / ``rework_status="vague"``.
Routing: error → END; success → ``deterministic_validate_question_patches``.
"""

from __future__ import annotations

import json
from typing import Any, cast

from src.api.control.quiz_agent.states.quiz_graph.quiz_state import QuizGraphState
from src.api.utils.quiz_utils.generation.question_parsing import (
    normalize_parsed_items,
    parse_json_array,
)
from src.api.utils.quiz_utils.graph.node_helpers import log_quiz_artifact


def _restore_patch_order_indices(
    patches: list[dict[str, Any]],
    all_questions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Re-attach ``order_index`` from the live quiz so DB patch order is preserved."""
    order_by_id = {
        str(question.get("question_id", "")).strip(): question.get("order_index")
        for question in all_questions
        if str(question.get("question_id", "")).strip()
    }
    restored: list[dict[str, Any]] = []
    for patch in patches:
        updated = dict(patch)
        question_id = str(updated.get("question_id", "")).strip()
        if question_id in order_by_id:
            updated["order_index"] = order_by_id[question_id]
        restored.append(updated)
    return restored


def _parse_vague_regen_response(raw: str) -> dict[str, Any] | None:
    """Detect LLM ``rework_status: vague`` JSON when feedback cannot be applied."""
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text
        if text.endswith("```"):
            text = text[: -len("```")]
        text = text.strip()
        if text.lower().startswith("json"):
            text = text[len("json") :].strip()
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return None
    if isinstance(parsed, dict) and parsed.get("rework_status") == "vague":
        return parsed
    return None


async def parse_quiz_single_regen_output(
    state: QuizGraphState,
) -> QuizGraphState:
    """Parse rework LLM output into ``parsed_patches`` with ID-set validation."""
    if state.get("parsed_patches") is not None:
        return state

    raw = state.get("raw_llm_output")
    if not raw:
        return {**state, "error": "No LLM output to parse."}

    vague = _parse_vague_regen_response(raw)
    if vague is not None:
        # Mentor feedback too vague — surface message to API layer via error state.
        message = str(
            vague.get("message")
            or "Feedback too vague to apply. Specify what to change."
        )
        return {
            **state,
            "rework_status": "vague",
            "error": message,
        }

    expected_ids = {str(question_id) for question_id in state.get("question_ids") or []}
    try:
        items = parse_json_array(raw)
        parsed, hints_stale_ids = normalize_parsed_items(items)
        parsed = _restore_patch_order_indices(
            parsed,
            state.get("all_questions") or [],
        )
    except Exception as exc:  # noqa: BLE001
        return {**state, "error": f"Malformed quiz single-question regen output: {exc}"}

    returned_ids = {str(patch.get("question_id", "")).strip() for patch in parsed}
    if returned_ids != expected_ids:
        return {
            **state,
            "error": (
                "Quiz single-question regen output must return exactly the requested question_ids."
            ),
        }

    if not hints_stale_ids:
        hints_stale_ids = list(expected_ids)

    log_quiz_artifact(
        cast(Any, state),
        "quiz_single_regen_parse",
        {
            "parsed_patches": parsed,
            "hints_stale_question_ids": hints_stale_ids,
        },
    )
    return {
        **state,
        "parsed_patches": parsed,
        "hints_stale_question_ids": hints_stale_ids,
    }
