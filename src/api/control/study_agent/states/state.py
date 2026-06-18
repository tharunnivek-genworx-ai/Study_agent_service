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
    improve_status: Literal["generated", "vague"] | None
    regenerate_status: Literal["generated", "vague"] | None
    llm_output_content: str

    # ── Quality-Check fields ──────────────────────────────────────
    qc_passed: bool  # True when QC evaluation passed
    qc_result: dict[str, Any] | None  # Full parsed JSON report from QC LLM
    qc_feedback: str  # Formatted QC issues for the retry prompt
    qc_attempt: int  # Number of QC evaluations so far (max 3)
    qc_failed_permanently: bool  # True when all 3 QC attempts failed
    failed_qc_feedback: str | None  # Previously failed QC feedback context from DB
