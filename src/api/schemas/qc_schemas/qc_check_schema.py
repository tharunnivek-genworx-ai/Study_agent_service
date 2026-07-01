"""QC verification check items, scores, and LLM response contract."""

from __future__ import annotations

from typing import Any, Literal, cast

from pydantic import BaseModel, Field

from src.api.schemas.common import QualityCheckItemOut

QcSeverity = Literal["critical", "major", "minor"]
QcOverallStatus = Literal["pass", "warn", "fail"]
QcHallucinationRisk = Literal["none", "low", "medium", "high"]

QcProseCategory = Literal[
    "must_cover",
    "content_accuracy",
    "teaching_alignment",
    "document_coherence",
]
QcCodeCategory = Literal["code_quality", "stack_fidelity"]
QcStructureCategory = Literal["structure"]
QcCategory = Literal[
    "must_cover",
    "content_accuracy",
    "teaching_alignment",
    "document_coherence",
    "code_quality",
    "stack_fidelity",
    "structure",
]

PROSE_CATEGORIES: frozenset[str] = frozenset(
    {"must_cover", "content_accuracy", "teaching_alignment", "document_coherence"}
)
CODE_CATEGORIES: frozenset[str] = frozenset({"code_quality", "stack_fidelity"})
VERIFICATION_CATEGORIES: frozenset[str] = PROSE_CATEGORIES | CODE_CATEGORIES


class QcCheckItem(BaseModel):
    """Single binary QC check from a verification pass."""

    id: str
    category: str
    question: str = ""
    passed: bool
    severity: QcSeverity = "minor"
    evidence: str = ""
    corrective_hint: str = ""
    section_id: str | None = None
    checklist_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(exclude_none=True)

    def to_quality_check_item_out(self) -> QualityCheckItemOut:
        return QualityCheckItemOut(
            id=self.id,
            category=self.category,
            question=self.question,
            passed=self.passed,
            severity=self.severity,
            evidence=self.evidence,
            corrective_hint=self.corrective_hint,
            section_id=self.section_id,
            checklist_id=self.checklist_id,
        )


def parse_qc_check_item(raw: dict[str, Any]) -> QcCheckItem | None:
    """Best-effort parse of a raw check dict from LLM or graph state."""
    try:
        return QcCheckItem(
            id=str(raw.get("id", "")),
            category=str(raw.get("category", "")),
            question=str(raw.get("question", "")),
            passed=bool(raw.get("passed", False)),
            severity=cast(QcSeverity, raw.get("severity", "minor")),
            evidence=str(raw.get("evidence", "")),
            corrective_hint=str(raw.get("corrective_hint", "")),
            section_id=str(raw.get("section_id", "")).strip() or None,
            checklist_id=str(raw.get("checklist_id", "")).strip() or None,
        )
    except Exception:
        return None


class QcScores(BaseModel):
    """Derived dimension scores (1–10) from binary checks."""

    structure: int | None = None
    content_accuracy: int | None = None
    code_quality: int | None = None
    section_depth: int | None = None
    teaching_alignment: int | None = None
    readability: int | None = None

    @classmethod
    def from_dict(cls, scores: dict[str, Any]) -> QcScores:
        return cls.model_validate(scores)


# Public API alias — same shape as internal ``QcScores``.
QualityCheckScoresOut = QcScores


class QcRetryRecommendation(BaseModel):
    mode: str = ""
    rationale: str = ""


class QcVerificationResult(BaseModel):
    """LLM QC verification pass output contract."""

    checks: list[QcCheckItem] = Field(default_factory=list)
    hallucination_risk: QcHallucinationRisk = "none"
    is_refusal: bool = False
    issues: list[str] = Field(default_factory=list)
    corrective_instructions: str = ""
    summary: str = ""
    retry_recommendation: QcRetryRecommendation | dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(exclude_none=True)


def is_valid_qc_verification_response(obj: dict[str, Any]) -> bool:
    """True when parsed JSON matches the QC verification contract.

    Requires a ``checks`` list. Empty ``checks`` is allowed only for refusals.
    """
    if "checks" not in obj:
        return False
    checks = obj["checks"]
    if not isinstance(checks, list):
        return False
    if obj.get("is_refusal"):
        return True
    if not checks:
        return False
    return True
