"""Build the LLM prompt for single-question mentor rework."""

from __future__ import annotations

from src.api.control.quiz_agent.prompts.quiz_graph.quiz_single_regen_prompt import (
    build_quiz_single_regen_prompt,
)
from src.api.control.quiz_agent.states.quiz_graph.quiz_state import QuizGraphState


async def build_quiz_single_regen_prompt_node(
    state: QuizGraphState,
) -> QuizGraphState:
    question_ids = [str(question_id) for question_id in state["question_ids"]]
    prompt_input = build_quiz_single_regen_prompt(
        topic_title=state.get("node_title") or str(state["node_id"]),
        study_material_content=state.get("study_material_content") or "",
        difficulty_profile=state.get("difficulty_profile") or "medium",
        mentor_feedback=state.get("mentor_feedback") or "",
        question_ids=question_ids,
        questions=state.get("all_questions") or [],
        domain=state.get("domain"),
        topic_split=state.get("topic_split"),
    )
    return {**state, "prompt_input": prompt_input}
