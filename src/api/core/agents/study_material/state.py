"""LangGraph state for study material generation (generate / regenerate / improve)."""

from typing import Any, Literal, TypedDict
from uuid import UUID

GenerationMode = Literal["generate", "regenerate", "improve"]


class StudyMaterialGraphState(TypedDict, total=False):
    node_id: UUID
    node_title: str
    reference_material_id: UUID | None
    reference_material_title: str | None
    reference_file_path: str | None
    reference_file_is_temp: bool
    has_reference_material: bool
    effective_instruction: str
    extracted_reference_text: str
    parsed_reference_data: dict[str, Any]
    generation_mode: GenerationMode
    skip_llamaparse: bool
    current_draft_content: str
    mentor_feedback: str
    generated_content: str
    prompt_snapshot: str
    token_usage: int
    llm_model_used: str
    error: str
