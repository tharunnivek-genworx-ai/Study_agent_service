"""LangGraph state for study material generation (generate / regenerate / improve)."""

from datetime import datetime
from typing import Any, Literal, TypedDict
from uuid import UUID

from src.api.schemas.common import GenerationMode
from src.api.schemas.study_material_schemas.generation_outcome_schema import (
    GraphGenerationOutcome,
)


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
    generation_outcome: GraphGenerationOutcome | None
    generation_outcome_detail: dict[str, Any] | None
    generation_parsed_document: dict[str, Any] | None
    generator_format_attempt: int
    prompt_snapshot: str
    token_usage: int
    llm_model_used: str
    error: str
    improve_status: Literal["generated", "vague"] | None
    regenerate_status: Literal["generated", "vague"] | None
    llm_output_content: str

    # ── Must-Cover Checklist fields ──────────────────────────────────
    domain: str  # STEM | Programming | Conceptual | Mixed — from concept checklist
    topic_split: list[dict[str, Any]]  # Section blueprint from concept checklist
    must_cover_checklist: list[
        dict[str, Any]
    ]  # Generated per run; reused across QC retries within generate only
    checklist_llm_model_used: str | None

    # ── Quality-Check fields ──────────────────────────────────────
    qc_evaluated: bool  # True only when QC node completes a verification pass
    qc_passed: bool  # True when QC evaluation passed
    qc_result: dict[str, Any] | None  # Full parsed JSON report from QC LLM
    qc_feedback: str  # Formatted QC issues for the retry prompt
    qc_attempt: int  # Number of QC evaluations so far (max 3)
    qc_failed_permanently: bool  # True when all 3 QC attempts failed
    failed_qc_feedback: str | None  # Previously failed QC feedback context from DB
    qc_extraction: (
        dict[str, Any] | None
    )  # Cached pass-1 extraction for logging/debugging
    qc_llm_model_used: str | None
    qc_llm_models_used: dict[str, str | None] | None
    qc_frozen_check_ids: list[str]  # Passed must_cover checklist ids — skip on retry QC
    qc_frozen_section_keys: list[
        str
    ]  # Section ids whose code blocks already passed QC — skip code checks on full retry
    qc_section_content_hashes: dict[
        str, str
    ]  # Section id → content hash baseline for frozen lineage validation
    fixed_sections: (
        list[dict[str, Any]] | None
    )  # Patched/inserted sections for targeted QC retry
    qc_verification_mode: (
        Literal["full", "targeted", "deterministic_only"] | None
    )  # Last QC LLM verification mode
    qc_retry_mode: Literal[
        "section_patch",
        "section_insert",
        "section_patch_then_insert",
        "full_regeneration",
        "none",
    ]
    qc_reverify_section_ids: list[str]  # Sections to fix / re-verify
    qc_missing_checklist_ids: list[str]  # Checklist ids with no section
    qc_section_failures: list[
        dict[str, Any]
    ]  # Per-section failure bundle for rework prompt
    qc_failure_class: (
        Literal["placement_only", "substance", "mixed", "none"] | None
    )  # Failure taxonomy from classify_retry_routing
    qc_relocation_plans: (
        list[dict[str, Any]] | None
    )  # Low-confidence plans for LLM fallback
    qc_placement_section_failures: list[dict[str, Any]] | None
    qc_substance_section_failures: list[dict[str, Any]] | None
    artifact_run_id: (
        str | None
    )  # IST stamp grouping per-agent artifacts for one graph run

    # ── LLM failure diagnostics ─────────────────────────────────────
    terminal_llm_failure: bool
    llm_error_type: str | None
    provider_meta: dict[str, Any] | None
    next_llm_retry_at: datetime | None
