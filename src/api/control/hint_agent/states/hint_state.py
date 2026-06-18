"""TypedDict state definitions for the quiz and hint generation LangGraphs.

Both state classes are plain ``TypedDict`` (no Pydantic, no dataclasses) and use
``total=False`` so individual nodes may return partial updates that LangGraph
merges into the running state.
"""

from typing import TypedDict
from uuid import UUID


class HintGraphState(TypedDict, total=False):
    mentor_id: UUID
    node_id: UUID
    quiz_id: UUID
    space_id: UUID | None
    questions_for_hinting: list | None
    questions_filter_ids: list | None  # optional list of UUID to limit hinting scope
    mentor_feedback: str | None
    prompt_input: dict | None
    raw_llm_output: str | None
    parsed_hints: list | None
    validated_hints: list | None
    token_usage: int | None
    llm_model_used: str | None
    error: str | None
