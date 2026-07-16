"""Parse raw LLM quiz output into structured question dicts.

Graph node (generate path)
--------------------------
Fallback parser when ``quiz_generator_node`` did not inline-parse. Skips work
if ``parsed_questions`` is already set (e.g. resume or retry path).

Inputs: ``raw_llm_output``.
Outputs: ``parsed_questions``, ``hints_stale_question_ids``, ``quiz_title``;
sets ``error`` when output is missing or malformed.

Routing: error → END; success → ``deterministic_validate``.
"""

from __future__ import annotations

from src.api.control.quiz_agent.states.quiz_graph.quiz_state import QuizGraphState
from src.api.utils.quiz_utils.generation.question_parsing import (
    normalize_parsed_items,
    parse_json_array,
)


async def parse_quiz_output(state: QuizGraphState) -> QuizGraphState:
    """Parse ``raw_llm_output`` into ``parsed_questions`` when not already present."""
    if state.get("parsed_questions") is not None:
        return state

    raw = state.get("raw_llm_output")
    if not raw:
        return {**state, "error": "No LLM output to parse."}

    try:
        items = parse_json_array(
            raw,
            expected_count=state.get("question_count"),
        )
        parsed, hints_stale_ids = normalize_parsed_items(items)
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
