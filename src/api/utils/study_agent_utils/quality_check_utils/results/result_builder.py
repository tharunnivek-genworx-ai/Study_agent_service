"""Merge structure + verification checks into a final QC result."""

from __future__ import annotations

from typing import Any

from src.api.schemas.qc_schemas.qc_check_schema import (
    CODE_CATEGORIES,
    PROSE_CATEGORIES,
)
from src.api.utils.study_agent_utils.generation.study_generation_json import (
    normalize_checklist_ids,
    normalize_must_cover_section_ids,
)
from src.api.utils.study_agent_utils.quality_check_utils.checks.deterministic import (
    attach_code_artifact_ids_from_document,
)
from src.api.utils.study_agent_utils.quality_check_utils.results.scoring import (
    derive_overall_status,
    derive_scores,
    extract_failed_checks,
    public_scores,
)

_DOCUMENT_LEVEL_CATEGORIES = frozenset({"teaching_alignment", "document_coherence"})


def _is_document_level_check(check: dict[str, Any]) -> bool:
    category = str(check.get("category", ""))
    if category not in _DOCUMENT_LEVEL_CATEGORIES:
        return False
    return not str(check.get("section_id", "") or "").strip()


def dedup_document_level_checks(checks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep one document-level check per category (last-wins).

    Prevents duplicate LLM emissions for teaching_alignment or document_coherence
    without a section_id from collapsing the derived score to 1.
    """
    last_index: dict[str, int] = {}
    for index, check in enumerate(checks):
        if _is_document_level_check(check):
            last_index[str(check.get("category", ""))] = index

    if not last_index:
        return checks

    superseded = {
        index
        for index, check in enumerate(checks)
        if _is_document_level_check(check)
        and last_index[str(check.get("category", ""))] != index
    }
    return [check for index, check in enumerate(checks) if index not in superseded]


def split_verification_checks(
    verification: dict[str, Any] | None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Split unified verification checks into prose vs code categories."""
    checks = list((verification or {}).get("checks", []) or [])
    prose_checks = [c for c in checks if c.get("category") in PROSE_CATEGORIES]
    code_checks = [c for c in checks if c.get("category") in CODE_CATEGORIES]
    return prose_checks, code_checks


def qc_models_used(
    prose_model: str | None,
    code_model: str | None,
) -> dict[str, str | None]:
    return {"prose": prose_model, "code": code_model}


def build_final_qc_result(
    verification: dict[str, Any] | None,
    structure_checks: list[dict[str, Any]],
    *,
    document: dict[str, Any],
    checklist: list[dict[str, Any]],
    model: str | None,
) -> dict[str, Any]:
    """Merge structure + verification checks and derive status/scores."""
    prose_checks, code_checks = split_verification_checks(verification)
    prose_checks = normalize_checklist_ids(prose_checks, checklist)
    prose_checks = normalize_must_cover_section_ids(prose_checks, checklist)
    code_checks = attach_code_artifact_ids_from_document(code_checks, document)

    all_checks = dedup_document_level_checks(
        structure_checks + prose_checks + code_checks
    )

    ver = verification or {}
    hallucination_risk = str(ver.get("hallucination_risk", "none"))
    is_refusal = bool(ver.get("is_refusal", False))

    issues = list(ver.get("issues", []) or [])

    overall_status = derive_overall_status(all_checks, hallucination_risk, is_refusal)
    scores = public_scores(derive_scores(all_checks))
    failed = extract_failed_checks(all_checks)

    corrective = str(ver.get("corrective_instructions", "")).strip()
    summary = str(ver.get("summary", "")).strip()

    result: dict[str, Any] = {
        "overall_status": overall_status,
        "is_refusal": is_refusal,
        "hallucination_risk": hallucination_risk,
        "scores": scores,
        "checks": all_checks,
        "failed_checks": failed,
        "issues": issues,
        "corrective_instructions": corrective,
        "summary": summary,
        "qc_llm_model_used": model,
        "qc_llm_models_used": qc_models_used(model, None),
    }

    recommendation = ver.get("retry_recommendation")
    if isinstance(recommendation, dict):
        result["retry_recommendation"] = recommendation

    return result
