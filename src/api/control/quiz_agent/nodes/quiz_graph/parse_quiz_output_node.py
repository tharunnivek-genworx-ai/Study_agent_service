"""Parse raw LLM quiz output into structured question dicts."""

from __future__ import annotations

from src.api.control.quiz_agent.states.quiz_graph.quiz_state import QuizGraphState
from src.api.utils.quiz_utils.generation.question_parsing import (
    normalize_parsed_items,
    parse_json_array,
)


async def parse_quiz_output(state: QuizGraphState) -> QuizGraphState:
    if state.get("parsed_questions") is not None:
        return state

    raw = state.get("raw_llm_output")
    if not raw:
        return {**state, "error": "No LLM output to parse."}

    try:
        items = parse_json_array(raw)
        parsed, hints_stale_ids = normalize_parsed_items(items, state)
    except Exception as exc:  # noqa: BLE001
        return {**state, "error": f"Malformed quiz output: {exc}"}

    quiz_title = (
        state.get("quiz_title") or f"{state.get('node_title') or 'Quiz'} — Quiz"
    )
    return {
        **state,
        "parsed_questions": parsed,
        "hints_stale_question_ids": hints_stale_ids,
        "quiz_title": quiz_title,
    }
