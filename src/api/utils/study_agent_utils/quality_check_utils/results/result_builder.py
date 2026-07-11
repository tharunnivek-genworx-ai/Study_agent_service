"""Merge structure + verification checks into a final QC result.

Pipeline role
-------------
Called once per ``quality_check_node`` visit after LLM verification (full or
targeted). Combines:

  1. **Deterministic checks** — ``det_structure_coverage``, ``det_equation_in_content``,
     etc. from ``structure_checks``
  2. **LLM prose checks** — must_cover, content_accuracy, teaching_alignment, ...
  3. **LLM code checks** — code_quality, stack_fidelity (with section_id attachment)

Then derives ``overall_status``, dimension ``scores``, ``failed_checks``, and
passes through LLM ``retry_recommendation`` for ``classify_retry_routing``.
"""

from __future__ import annotations

from typing import Any

from src.api.schemas.qc_schemas import (
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


def _is_no_action_needed_hint(corrective_hint: Any) -> bool:
    hint = str(corrective_hint or "").strip().lower()
    return hint.startswith("no action needed")


def reconcile_no_action_needed_checks(
    checks: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Flip passed=true when the LLM corrective_hint explicitly says no fix is required."""
    reconciled: list[dict[str, Any]] = []
    for check in checks:
        if not check.get("passed", True) and _is_no_action_needed_hint(
            check.get("corrective_hint")
        ):
            updated = dict(check)
            updated["passed"] = True
            updated["corrective_hint"] = ""
            reconciled.append(updated)
        else:
            reconciled.append(check)
    return reconciled


def build_final_qc_result(
    verification: dict[str, Any] | None,
    structure_checks: list[dict[str, Any]],
    *,
    document: dict[str, Any],
    checklist: list[dict[str, Any]],
    model: str | None,
) -> dict[str, Any]:
    """Merge deterministic + LLM checks and derive QC report fields.

    Normalizes must_cover checklist/section ids, attaches code artifact section
    ids, deduplicates document-level teaching_alignment/document_coherence checks,
    and computes scores via ``derive_scores`` / ``derive_overall_status``.

    Args:
        verification: Raw LLM verification JSON (or targeted pass output).
        structure_checks: Deterministic checks from QC node phase 1.
        document: Parsed study document (for code block → section mapping).
        checklist: must_cover checklist for id normalization.
        model: QC LLM model id for metadata.

    Returns:
        Dict written to ``state["qc_result"]`` and ``05_qc_result.json`` artifact.
    """
    prose_checks, code_checks = split_verification_checks(verification)
    prose_checks = normalize_checklist_ids(prose_checks, checklist)
    prose_checks = normalize_must_cover_section_ids(prose_checks, checklist)
    prose_checks = reconcile_no_action_needed_checks(prose_checks)
    code_checks = attach_code_artifact_ids_from_document(code_checks, document)
    code_checks = reconcile_no_action_needed_checks(code_checks)

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
