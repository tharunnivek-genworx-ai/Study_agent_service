# src/api/utils/study_agent_utils/qc/scoring.py
"""Pure-Python QC status and score derivation — no LLM.

``quality_check_node`` uses:
  - ``derive_overall_status`` → pass | warn | fail
  - ``derive_scores`` / ``public_scores`` → dimension scores 1–10
  - ``is_qc_deliverable`` → whether graph may END despite ``warn`` status
  - ``extract_failed_checks`` → input to ``classify_retry_routing``

Score buckets: ``section_depth`` bundles must_cover + document_coherence (includes
deterministic ``det_*`` checks with category document_coherence).
"""

from __future__ import annotations

from typing import Any


def derive_overall_status(
    checks: list[dict[str, Any]],
    hallucination_risk: str,
    is_refusal: bool,
) -> str:
    """Derive the overall QC status from binary check results."""
    if is_refusal:
        return "pass"
    if hallucination_risk == "high":
        return "fail"
    if any(
        not c.get("passed", True) and c.get("severity") == "critical" for c in checks
    ):
        return "fail"
    if hallucination_risk == "medium":
        return "warn"
    if any(not c.get("passed", True) and c.get("severity") == "major" for c in checks):
        return "warn"
    if any(not c.get("passed", True) for c in checks):
        return "warn"
    return "pass"


_CATEGORY_TO_SCORE_KEY: dict[str, str] = {
    "structure": "structure",
    "content_accuracy": "content_accuracy",
    "code_quality": "code_quality",
    "stack_fidelity": "code_quality",
    "teaching_alignment": "teaching_alignment",
    "pitfalls_depth": "section_depth",
    "concept_coverage": "section_depth",
    "must_cover": "section_depth",
    "document_coherence": "section_depth",
}


def _score_from_checks(checks_for_key: list[dict[str, Any]]) -> int | None:
    if not checks_for_key:
        return None
    passed = sum(1 for c in checks_for_key if c.get("passed", False))
    total = len(checks_for_key)
    raw = round(passed / total * 10)
    return max(1, min(10, raw))


def derive_scores(checks: list[dict[str, Any]]) -> dict[str, int | None]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for check in checks:
        category = check.get("category", "")
        score_key = _CATEGORY_TO_SCORE_KEY.get(category)
        if score_key:
            grouped.setdefault(score_key, []).append(check)

    score_keys = [
        "structure",
        "content_accuracy",
        "code_quality",
        "section_depth",
        "teaching_alignment",
    ]
    return {key: _score_from_checks(grouped.get(key, [])) for key in score_keys}


_INTERNAL_SCORE_KEYS = frozenset({"structure", "readability"})


def public_scores(scores: dict[str, int | None]) -> dict[str, int | None]:
    """Return API/DB-facing scores without internal-only routing dimensions."""
    return {
        key: value for key, value in scores.items() if key not in _INTERNAL_SCORE_KEYS
    }


def extract_failed_checks(checks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [c for c in checks if not c.get("passed", True)]


def has_failed_must_cover(failed_checks: list[dict[str, Any]]) -> bool:
    """True when any must_cover checklist item failed QC."""
    return any(
        str(check.get("category", "")) == "must_cover" and not check.get("passed", True)
        for check in failed_checks
    )


def missing_checklist_ids_from_recommendation(
    retry_recommendation: dict[str, Any] | None,
) -> list[str]:
    if not isinstance(retry_recommendation, dict):
        return []
    return [
        str(item_id).strip()
        for item_id in (retry_recommendation.get("missing_checklist_ids") or [])
        if str(item_id).strip()
    ]


def _document_section_ids(document: dict[str, Any] | None) -> set[str]:
    if not isinstance(document, dict):
        return set()
    return {
        str(section.get("id", "")).strip()
        for section in document.get("sections") or []
        if isinstance(section, dict) and str(section.get("id", "")).strip()
    }


def _checklist_item_by_id(
    checklist: list[dict[str, Any]],
    item_id: str,
) -> dict[str, Any] | None:
    for item in checklist:
        if str(item.get("id", "")).strip() == item_id:
            return item
    return None


def _must_cover_passed_for_id(
    checks: list[dict[str, Any]],
    *,
    item_id: str,
) -> bool | None:
    """Return True/False when a must_cover check for ``item_id`` exists, else None."""
    for check in checks:
        if str(check.get("category", "")) != "must_cover":
            continue
        check_item = str(check.get("checklist_id") or check.get("id") or "").strip()
        # Accept bare mc_* ids and must_cover_mc_* / must_cover_<id> forms.
        if check_item in {item_id, f"must_cover_{item_id}"}:
            return bool(check.get("passed", True))
        if check_item.endswith(f"_{item_id}") and item_id:
            return bool(check.get("passed", True))
    return None


def _derive_mode_from_targets(
    *,
    failed_section_ids: list[str],
    missing_checklist_ids: list[str],
    previous_mode: str,
) -> str:
    has_failed = bool(failed_section_ids)
    has_missing = bool(missing_checklist_ids)
    if not has_failed and not has_missing:
        return "none"
    if has_failed and has_missing:
        return "section_patch_then_insert"
    if has_missing:
        return "section_insert"
    if previous_mode == "full_regeneration":
        # Keep full regen only when there is still at least one failed section target.
        return "full_regeneration"
    return "section_patch"


def sanitize_retry_recommendation(
    recommendation: dict[str, Any] | None,
    *,
    checks: list[dict[str, Any]],
    document: dict[str, Any] | None = None,
    checklist: list[dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    """Drop contradictory LLM retry targets; recompute mode from remaining targets.

    Guards the Calvin-style failure mode where every check passes but the model
    still emits ``missing_checklist_ids`` / ``section_patch`` for an existing
    section, which previously forced a non-deliverable result with
    ``qc_retry_mode=none`` (blind full regenerate).
    """
    if not isinstance(recommendation, dict):
        return None

    from src.api.utils.study_agent_utils.generation.study_generation_json import (
        normalize_checklist_id,
    )

    checklist = checklist or []
    known_sections = _document_section_ids(document)
    failed_checks = extract_failed_checks(checks)

    cleaned_failed_sections: list[str] = []
    seen_sections: set[str] = set()
    for raw in recommendation.get("failed_section_ids") or []:
        section_id = str(raw).strip()
        if not section_id or section_id in seen_sections:
            continue
        if known_sections and section_id not in known_sections:
            continue
        if not failed_checks:
            # All checks passed → never keep patch targets from the recommendation.
            continue
        # When checks failed (including document-level checks without section_id),
        # allow the LLM to map targets onto existing sections.
        cleaned_failed_sections.append(section_id)
        seen_sections.add(section_id)

    cleaned_missing: list[str] = []
    seen_missing: set[str] = set()
    for raw in recommendation.get("missing_checklist_ids") or []:
        item_id = (
            normalize_checklist_id(str(raw), checklist)
            if checklist
            else str(raw).strip()
        )
        item_id = str(item_id).strip()
        if not item_id or item_id in seen_missing:
            continue

        passed = _must_cover_passed_for_id(checks, item_id=item_id)
        if passed is True:
            continue

        item = _checklist_item_by_id(checklist, item_id) if checklist else None
        section_id = str(item.get("section_id") or item_id).strip() if item else item_id
        if known_sections and section_id in known_sections:
            # Section exists → not an insert target (may still be a patch if failed).
            continue

        cleaned_missing.append(item_id)
        seen_missing.add(item_id)

    previous_mode = str(recommendation.get("mode") or "none").strip() or "none"
    mode = _derive_mode_from_targets(
        failed_section_ids=cleaned_failed_sections,
        missing_checklist_ids=cleaned_missing,
        previous_mode=previous_mode,
    )
    # Preserve explicit full_regeneration only when there are real failed checks.
    if previous_mode == "full_regeneration" and failed_checks:
        mode = "full_regeneration"

    rationale = str(recommendation.get("rationale") or "").strip()
    if mode == "none" and previous_mode != "none":
        rationale = (
            "Sanitized contradictory retry_recommendation "
            f"(was {previous_mode!r}; all actionable targets dropped)."
        )

    return {
        "mode": mode,
        "failed_section_ids": cleaned_failed_sections,
        "missing_checklist_ids": cleaned_missing,
        "rationale": rationale,
    }


def requires_must_cover_retry(
    *,
    failed_checks: list[dict[str, Any]],
    retry_recommendation: dict[str, Any] | None,
) -> bool:
    """True when checklist gaps remain and the pipeline should retry generation.

    ``missing_checklist_ids`` alone only counts after sanitization (or when the
    caller already dropped contradictory ids). Prefer passing a sanitized
    recommendation from ``build_final_qc_result``.
    """
    if has_failed_must_cover(failed_checks):
        return True
    return bool(missing_checklist_ids_from_recommendation(retry_recommendation))


def is_qc_deliverable(
    *,
    overall_status: str,
    failed_checks: list[dict[str, Any]],
    hallucination_risk: str,
    is_refusal: bool,
    retry_recommendation: dict[str, Any] | None = None,
) -> bool:
    """Return True when QC result is deliverable despite overall_status nuances.

    ``warn`` is deliverable when no critical failures remain, hallucination risk
    is not high, and no must_cover checklist item failed or is missing.
    ``overall_status`` is unchanged for reporting.

    Spurious ``missing_checklist_ids`` on an otherwise-passing run must be
    sanitized before calling this (see ``sanitize_retry_recommendation``).
    """
    if is_refusal:
        return True
    if requires_must_cover_retry(
        failed_checks=failed_checks,
        retry_recommendation=retry_recommendation,
    ):
        return False
    if overall_status == "pass":
        return True
    if overall_status == "fail":
        return False
    if overall_status == "warn":
        if hallucination_risk == "high":
            return False
        if any(c.get("severity") == "critical" for c in failed_checks):
            return False
        return True
    return False
