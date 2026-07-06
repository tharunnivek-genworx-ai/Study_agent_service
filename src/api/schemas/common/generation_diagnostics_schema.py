"""Shared generation / QC diagnostics surfaced in API responses and JSONB qc_result."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

LlmErrorType = Literal[
    "rate_limited",
    "token_limit",
    "llm_infra_error",
    "llm_key_pool_exhausted",
    "hint_quality_error",
    "qc_extraction_failed",
    "qc_verification_failed",
]

QcInfraErrorType = Literal[
    "llm_infra_error",
    "rate_limited",
    "token_limit",
    "llm_key_pool_exhausted",
    "qc_extraction_failed",
    "qc_verification_failed",
]

HintErrorType = Literal[
    "rate_limited",
    "token_limit",
    "llm_infra_error",
    "llm_key_pool_exhausted",
    "hint_quality_error",
]


class ProviderMetaOut(BaseModel):
    """Provider attempt metadata for LLM failure diagnostics."""

    model_config = ConfigDict(populate_by_name=True)

    api_key_alias: str | None = Field(default=None, alias="apiKeyAlias")
    attempt_index: int | None = Field(default=None, alias="attemptIndex")
    graph_node: str | None = Field(default=None, alias="graphNode")
    retry_after_seconds: int | None = Field(default=None, alias="retryAfterSeconds")
    next_llm_retry_at: datetime | None = Field(default=None, alias="nextLlmRetryAt")


class HintQuestionErrorOut(BaseModel):
    """Per-question hint generation failure."""

    model_config = ConfigDict(populate_by_name=True)

    question_id: UUID
    error_type: HintErrorType = Field(alias="errorType")
    attempts: int


class HintGenerationDiagnosticsOut(BaseModel):
    """Hint-agent diagnostics merged into quizzes.qc_result.hintGeneration."""

    model_config = ConfigDict(populate_by_name=True)

    error_type: HintErrorType | None = Field(default=None, alias="errorType")
    question_errors: list[HintQuestionErrorOut] = Field(
        default_factory=list, alias="questionErrors"
    )
    retry_after_seconds: int | None = Field(default=None, alias="retryAfterSeconds")
    next_llm_retry_at: datetime | None = Field(default=None, alias="nextLlmRetryAt")


class GenerationDiagnosticsFlaggedQuestionOut(BaseModel):
    """Flagged question entry embedded in generation diagnostics."""

    question_id: UUID
    question_number: int
    flags: list[str] = Field(default_factory=list)


class QualityCheckItemOut(BaseModel):
    """Single binary QC check from the verification pass."""

    id: str
    category: str
    question: str
    passed: bool
    severity: Literal["critical", "major", "minor"]
    evidence: str = ""
    corrective_hint: str = ""
    section_id: str | None = None
    checklist_id: str | None = None


class DetFailureDisplayOut(BaseModel):
    check_id: str
    section_label: str
    subsection_label: str | None = None
    user_message: str
    tier: Literal["formatting", "structure", "evidence"]


class QcWarningPresentationOut(BaseModel):
    kind: Literal["det_only", "llm_content", "mixed"]
    alert_title: str
    alert_body: str
    det_summary: str | None = None
    reassurance: str | None = None
    formatting_items: list[DetFailureDisplayOut] = Field(default_factory=list)
    structure_items: list[DetFailureDisplayOut] = Field(default_factory=list)
    evidence_items: list[DetFailureDisplayOut] = Field(default_factory=list)
    formatting_list_label: str
    structure_list_label: str
    evidence_list_label: str
    det_only_list_label: str
    is_formatting_only: bool = False
    content_issues_label: str


class GenerationDiagnosticsOut(BaseModel):
    """Superset QC + LLM failure payload stored in qc_result and returned to clients.

    Content-QC fields (study or quiz) are optional so LLM infra failures can be
    represented without a full quality evaluation. New LLM diagnostic keys use
    camelCase aliases for frontend consumption.
    """

    model_config = ConfigDict(populate_by_name=True)

    # ── Study material content QC (optional) ──────────────────────────────
    overall_status: Literal["pass", "warn", "fail"] | None = None
    is_refusal: bool | None = None
    hallucination_risk: Literal["none", "low", "medium", "high"] | None = None

    # ── Quiz content QC (optional) ────────────────────────────────────────
    wrong_answer_risk: Literal["none", "low", "medium", "high"] | None = None
    flagged_questions: list[GenerationDiagnosticsFlaggedQuestionOut] | None = None

    # ── Shared content QC ─────────────────────────────────────────────────
    scores: dict[str, Any] | None = None
    checks: list[QualityCheckItemOut] | None = None
    issues: list[str] = Field(default_factory=list)
    humanized_issues: list[str] | None = None
    corrective_instructions: str = ""
    humanized_corrective_instructions: str | None = None
    summary: str = ""
    warning_presentation: QcWarningPresentationOut | None = None

    # ── Study material two-pass QC metadata (optional) ────────────────────
    must_cover_checklist: list[dict[str, Any]] | None = None
    qc_llm_model_used: str | None = Field(default=None, alias="qcLlmModelUsed")
    qc_llm_models_used: dict[str, str | None] | None = Field(
        default=None, alias="qcLlmModelsUsed"
    )
    checklist_llm_model_used: str | None = Field(
        default=None, alias="checklistLlmModelUsed"
    )
    qc_extraction: dict[str, Any] | None = Field(default=None, alias="qcExtraction")
    verification_mode: Literal["full", "targeted", "deterministic_only"] | None = Field(
        default=None, alias="verificationMode"
    )
    fixed_sections: list[dict[str, Any]] | None = Field(
        default=None, alias="fixedSections"
    )
    checks_carried_forward: int | None = Field(
        default=None, alias="checksCarriedForward"
    )
    checks_reverified: int | None = Field(default=None, alias="checksReverified")

    # ── LLM failure / infra diagnostics ───────────────────────────────────
    error_type: LlmErrorType | None = Field(default=None, alias="errorType")
    qc_infra_error: bool | None = Field(default=None, alias="qcInfraError")
    provider_meta: ProviderMetaOut | None = Field(default=None, alias="providerMeta")
    suggestion: str | None = None
    retry_after_seconds: int | None = Field(default=None, alias="retryAfterSeconds")
    next_llm_retry_at: datetime | None = Field(default=None, alias="nextLlmRetryAt")
    hint_generation: HintGenerationDiagnosticsOut | None = Field(
        default=None, alias="hintGeneration"
    )
