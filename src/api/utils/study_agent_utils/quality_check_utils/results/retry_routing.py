# src/api/utils/study_agent_utils/qc/retry_routing.py
"""Map QC failures to study-agent retry mode and per-section rework targets.

Pipeline position
-----------------
Called at end of ``quality_check_node`` after ``build_final_qc_result``.

Outputs ``RetryRoutingResult`` consumed by ``routing_state`` → graph fields:
  - ``qc_retry_mode``: section_patch | section_insert | patch_then_insert |
    full_regeneration | none
  - ``qc_reverify_section_ids``: document section ids to patch
  - ``qc_missing_checklist_ids``: checklist/topic_split ids needing insert
  - ``qc_section_failures``: bundles for ``section_rework_prompt`` (not flat qc_feedback)

Routing rules (simplified):
  - ``must_cover`` fail + section exists → patch; no section → insert
  - ``det_*`` / ``content_accuracy`` / etc. with ``section_id`` → patch
  - ``det_structure_coverage`` → insert targets (handled outside generic mapper)
  - ``teaching_alignment`` → may force full_regeneration (no section_id)
  - ≥4 failed sections or ≥40% required checklist affected → full_regeneration

Deterministic ``det_equation_in_content`` failures default to **section_patch**
(not full regen) unless escalation thresholds fire.
"""

from __future__ import annotations

from typing import Any, cast

from src.api.schemas.qc_schemas import (
    RetryMode,
    RetryRoutingResult,
)
from src.api.utils.study_agent_utils.generation.study_generation_json import (
    expected_document_section_ids,
    normalize_checklist_id,
    resolve_checklist_section_id,
    validate_section_id_coverage,
)
from src.api.utils.study_agent_utils.quality_check_utils.core.failure_class import (
    classify_failure_class,
    failed_must_cover_checklist_ids,
    is_placement_only_failure,
    split_section_failures_by_kind,
)
from src.api.utils.study_agent_utils.quality_check_utils.results.scoring import (
    sanitize_retry_recommendation,
)

_VALID_MODES: frozenset[str] = frozenset(
    {
        "section_patch",
        "section_insert",
        "section_patch_then_insert",
        "full_regeneration",
        "none",
    }
)

_FULL_REGEN_FAILED_SECTION_THRESHOLD = 4
_FULL_REGEN_COVERAGE_THRESHOLD = 0.4
_WIDESPREAD_STRUCTURE_GAP_THRESHOLD = 0.4


def _required_checklist_ids(checklist: list[dict[str, Any]]) -> set[str]:
    return {
        str(item.get("id", "")).strip()
        for item in checklist
        if str(item.get("priority", "")).lower() == "required" and item.get("id")
    }


def _document_section_ids(document: dict[str, Any]) -> set[str]:
    return {
        str(section.get("id", "")).strip()
        for section in document.get("sections") or []
        if isinstance(section, dict) and section.get("id") is not None
    }


def _section_by_id(document: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(section.get("id", "")).strip(): section
        for section in document.get("sections") or []
        if isinstance(section, dict) and str(section.get("id", "")).strip()
    }


def _failed_checks(qc_result: dict[str, Any]) -> list[dict[str, Any]]:
    explicit = qc_result.get("failed_checks")
    if isinstance(explicit, list) and explicit:
        return [check for check in explicit if isinstance(check, dict)]

    checks = qc_result.get("checks")
    if not isinstance(checks, list):
        return []
    return [
        check
        for check in checks
        if isinstance(check, dict) and not check.get("passed", True)
    ]


def _failure_record(check: dict[str, Any]) -> dict[str, str]:
    return {
        "check_id": str(check.get("id", "")),
        "category": str(check.get("category", "")),
        "evidence": str(check.get("evidence", "")),
        "corrective_hint": str(check.get("corrective_hint", "")),
    }


def _structure_coverage_failed(failed: list[dict[str, Any]]) -> bool:
    return any(
        str(check.get("id", "")) == "det_structure_coverage"
        and not check.get("passed", True)
        for check in failed
    )


def _is_structure_only_failure(failed: list[dict[str, Any]]) -> bool:
    """True when the only actionable failure is missing section ids."""
    actionable = [
        check
        for check in failed
        if str(check.get("category", "")) != "teaching_alignment"
    ]
    return (
        len(actionable) == 1
        and str(actionable[0].get("id", "")) == "det_structure_coverage"
        and not actionable[0].get("passed", True)
    )


def _checklist_ids_for_missing_sections(
    missing_section_ids: set[str],
    checklist: list[dict[str, Any]],
) -> set[str]:
    checklist_ids: set[str] = set()
    for item in checklist:
        item_id = str(item.get("id", "")).strip()
        section_id = str(item.get("section_id", "")).strip() or item_id
        if section_id in missing_section_ids and item_id:
            checklist_ids.add(item_id)
    return checklist_ids


def _affected_required_checklist_ids(
    *,
    checklist: list[dict[str, Any]],
    failed: list[dict[str, Any]],
    missing_checklist_ids: set[str],
) -> set[str]:
    """Required checklist ids that are missing or failed on must_cover."""
    required = _required_checklist_ids(checklist)
    if not required:
        return set()
    affected = set(missing_checklist_ids)
    affected |= failed_must_cover_checklist_ids(failed, checklist)
    return affected & required


def _missing_section_ids_from_structure(
    *,
    document: dict[str, Any],
    checklist: list[dict[str, Any]],
    topic_split: list[dict[str, Any]] | None = None,
) -> set[str]:
    coverage = validate_section_id_coverage(
        document, checklist, topic_split=topic_split
    )
    return set(coverage.missing_ids)


def _resolve_structure_missing_ids(
    *,
    document: dict[str, Any],
    checklist: list[dict[str, Any]],
    topic_split: list[dict[str, Any]] | None = None,
    structure_missing_ids: set[str] | frozenset[str] | None = None,
) -> set[str]:
    if structure_missing_ids is not None:
        return set(structure_missing_ids)
    return _missing_section_ids_from_structure(
        document=document,
        checklist=checklist,
        topic_split=topic_split,
    )


def _enrich_missing_checklist_from_structure(
    missing_checklist_ids: set[str],
    structure_missing: set[str],
    *,
    checklist: list[dict[str, Any]],
    topic_split: list[dict[str, Any]] | None = None,
) -> None:
    """Map missing document section ids to checklist or topic_split insert targets."""
    for section_id in structure_missing:
        mapped = _checklist_ids_for_missing_sections({section_id}, checklist)
        if mapped:
            missing_checklist_ids |= mapped
        elif topic_split and any(
            str(entry.get("id", "")).strip() == section_id
            for entry in topic_split
            if isinstance(entry, dict)
        ):
            missing_checklist_ids.add(section_id)


def _map_failures_to_targets(
    failed: list[dict[str, Any]],
    *,
    document: dict[str, Any],
    checklist: list[dict[str, Any]],
    topic_split: list[dict[str, Any]] | None = None,
    structure_missing_ids: set[str] | frozenset[str] | None = None,
) -> tuple[
    set[str],
    set[str],
    dict[str, list[dict[str, str]]],
    int,
    set[str] | None,
]:
    """Map each failed check to patch targets, insert targets, or unmapped.

    Category handling:
      - ``must_cover``: resolve ``mc_*`` → section id; patch if section exists
        else ``missing_checklist_ids``
      - ``teaching_alignment``: skipped here (document-level; full regen rules)
      - ``det_structure_coverage``: skipped here; enriched after loop
      - All others with ``section_id`` (``det_*``, ``content_accuracy``, …): patch

    Returns:
        ``(failed_section_ids, missing_checklist_ids, failures_by_section,
        unmapped_count, structure_missing)``
    """
    section_ids = _document_section_ids(document)
    failed_section_ids: set[str] = set()
    missing_checklist_ids: set[str] = set()
    failures_by_section: dict[str, list[dict[str, str]]] = {}
    unmapped_count = 0

    for check in failed:
        category = str(check.get("category", ""))

        if category == "must_cover":
            item_id = normalize_checklist_id(
                str(check.get("checklist_id") or check.get("id", "")),
                checklist,
            )
            if not item_id:
                unmapped_count += 1
                continue
            section_target = resolve_checklist_section_id(checklist, item_id)
            if section_target in section_ids:
                failed_section_ids.add(section_target)
                failures_by_section.setdefault(section_target, []).append(
                    _failure_record(check)
                )
            else:
                missing_checklist_ids.add(item_id)
            continue

        if category == "teaching_alignment":
            # Document-level check — no section_id; F1/F2/F7 → full_regeneration.
            continue

        # det_structure_coverage has no section_id; handled after the loop.
        if (
            category == "structure"
            and str(check.get("id", "")) == "det_structure_coverage"
        ):
            continue

        section_id = str(check.get("section_id", "")).strip()
        if section_id and section_id in section_ids:
            failed_section_ids.add(section_id)
            failures_by_section.setdefault(section_id, []).append(
                _failure_record(check)
            )
        else:
            unmapped_count += 1

    structure_missing: set[str] | None = None
    if _structure_coverage_failed(failed):
        structure_missing = _resolve_structure_missing_ids(
            document=document,
            checklist=checklist,
            topic_split=topic_split,
            structure_missing_ids=structure_missing_ids,
        )
        _enrich_missing_checklist_from_structure(
            missing_checklist_ids,
            structure_missing,
            checklist=checklist,
            topic_split=topic_split,
        )

    return (
        failed_section_ids,
        missing_checklist_ids,
        failures_by_section,
        unmapped_count,
        structure_missing,
    )


def _teaching_alignment_failed(failed: list[dict[str, Any]]) -> bool:
    for check in failed:
        if str(check.get("category", "")) != "teaching_alignment":
            continue
        if not check.get("passed", True):
            return True
    return False


def _teaching_alignment_critical_fail(failed: list[dict[str, Any]]) -> bool:
    for check in failed:
        if str(check.get("category", "")) != "teaching_alignment":
            continue
        if check.get("passed", True):
            continue
        if str(check.get("severity", "")).lower() == "critical":
            return True
    return False


def _structure_coverage_widespread(
    structure_missing: set[str],
    *,
    checklist: list[dict[str, Any]],
    topic_split: list[dict[str, Any]] | None = None,
) -> bool:
    missing_count = len(structure_missing)
    if missing_count <= 1:
        return False
    required = expected_document_section_ids(checklist, topic_split)
    if not required:
        return True
    gap_ratio = missing_count / len(required)
    return gap_ratio >= _WIDESPREAD_STRUCTURE_GAP_THRESHOLD


def _should_force_full_regeneration(
    *,
    failed: list[dict[str, Any]],
    failed_section_ids: set[str],
    missing_checklist_ids: set[str],
    checklist: list[dict[str, Any]],
    topic_split: list[dict[str, Any]] | None = None,
    unmapped_count: int,
    structure_missing: set[str] | None = None,
) -> tuple[bool, str]:
    """Escalate from section_patch to full_regeneration when failures are widespread.

    Triggers include: critical teaching_alignment, widespread structure gaps,
    ≥40% required checklist items affected, ≥4 distinct failed section ids,
    or ≥3 unmapped checks (LLM checks without valid section_id).
    """
    if is_placement_only_failure(failed):
        return False, ""

    if _teaching_alignment_critical_fail(failed):
        return True, "teaching_alignment critical failure"

    if _teaching_alignment_failed(failed) and unmapped_count >= 2:
        return True, "teaching_alignment failure with widespread unmapped checks"

    if structure_missing is not None and _structure_coverage_widespread(
        structure_missing,
        checklist=checklist,
        topic_split=topic_split,
    ):
        return True, "det_structure_coverage with widespread gaps"

    required = _required_checklist_ids(checklist)
    if required and not _is_structure_only_failure(failed):
        affected_required = _affected_required_checklist_ids(
            checklist=checklist,
            failed=failed,
            missing_checklist_ids=missing_checklist_ids,
        )
        ratio = len(affected_required) / len(required)
        if ratio >= _FULL_REGEN_COVERAGE_THRESHOLD:
            return (
                True,
                f"{len(affected_required)}/{len(required)} required checklist sections missing or failed",
            )

    if len(failed_section_ids) >= _FULL_REGEN_FAILED_SECTION_THRESHOLD:
        return True, f"{len(failed_section_ids)} distinct failed section ids"

    # F6: unmappable failures (LLM checks without valid section_id, etc.), not det_*.
    if unmapped_count >= 3:
        return True, f"{unmapped_count} unmapped failed checks"

    return False, ""


def _deterministic_mode(
    *,
    failed_section_ids: set[str],
    missing_checklist_ids: set[str],
) -> RetryMode:
    """Choose retry mode from patch vs insert targets (before LLM reconcile).

    - failed sections only → ``section_patch``
    - missing sections only → ``section_insert``
    - both → ``section_patch_then_insert``
    - neither → ``none``
    """
    has_failed = bool(failed_section_ids)
    has_missing = bool(missing_checklist_ids)
    if not has_failed and not has_missing:
        return "none"
    if has_failed and has_missing:
        return "section_patch_then_insert"
    if has_missing:
        return "section_insert"
    return "section_patch"


def _coerce_llm_recommendation_mode(raw_mode: Any) -> RetryMode | None:
    mode = str(raw_mode or "").strip()
    if mode in _VALID_MODES:
        return cast(RetryMode, mode)
    return None


def _merge_llm_recommendation_targets(
    *,
    recommendation: dict[str, Any] | None,
    document: dict[str, Any],
    checklist: list[dict[str, Any]],
    failed_section_ids: set[str],
    missing_checklist_ids: set[str],
    failures_by_section: dict[str, list[dict[str, str]]],
    failed: list[dict[str, Any]],
) -> None:
    """Fill routing targets from ``retry_recommendation`` when the mapper found none.

    Only runs when deterministic mapping produced no patch or insert targets, so
    existing scoped failures (must_cover, det_*, content_accuracy, …) are unchanged.
    """
    if failed_section_ids or missing_checklist_ids:
        return
    if not isinstance(recommendation, dict):
        return

    known = _document_section_ids(document)
    for raw in recommendation.get("failed_section_ids") or []:
        section_id = str(raw).strip()
        if section_id in known:
            failed_section_ids.add(section_id)

    for raw in recommendation.get("missing_checklist_ids") or []:
        item_id = normalize_checklist_id(str(raw), checklist)
        if item_id:
            missing_checklist_ids.add(item_id)

    if not failed_section_ids:
        return

    doc_level_failures = [
        _failure_record(check)
        for check in failed
        if not str(check.get("section_id", "") or "").strip()
    ]
    if not doc_level_failures:
        return

    for section_id in failed_section_ids:
        existing = failures_by_section.setdefault(section_id, [])
        if not existing:
            existing.extend(doc_level_failures)


def _teaching_alignment_sole_failure(failed: list[dict[str, Any]]) -> bool:
    """True when every failed check is document-level teaching_alignment."""
    if not failed:
        return False
    return all(
        str(check.get("category", "")) == "teaching_alignment" for check in failed
    )


def _reconcile_mode(
    *,
    deterministic: RetryMode,
    llm_recommendation_mode: RetryMode | None,
    force_full_regen: bool,
    failed_section_ids: set[str],
    missing_checklist_ids: set[str],
    teaching_alignment_sole_failure: bool,
) -> RetryMode:
    if force_full_regen:
        return "full_regeneration"
    if deterministic == "none":
        if teaching_alignment_sole_failure:
            return "full_regeneration"
        if llm_recommendation_mode and llm_recommendation_mode != "none":
            has_failed = bool(failed_section_ids)
            has_missing = bool(missing_checklist_ids)
            if llm_recommendation_mode == "full_regeneration":
                return "full_regeneration"
            if llm_recommendation_mode == "section_patch" and has_failed:
                return "section_patch"
            if llm_recommendation_mode == "section_insert" and has_missing:
                return "section_insert"
            if (
                llm_recommendation_mode == "section_patch_then_insert"
                and has_failed
                and has_missing
            ):
                return "section_patch_then_insert"
        return "none"

    if llm_recommendation_mode is None:
        return deterministic

    if llm_recommendation_mode == "none":
        return deterministic

    has_failed = bool(failed_section_ids)
    has_missing = bool(missing_checklist_ids)

    if llm_recommendation_mode == "section_patch" and has_failed and not has_missing:
        return "section_patch"
    if llm_recommendation_mode == "section_insert" and has_missing and not has_failed:
        return "section_insert"
    if (
        llm_recommendation_mode == "section_patch_then_insert"
        and has_failed
        and has_missing
    ):
        return "section_patch_then_insert"

    return deterministic


def _build_section_failures(
    failed_section_ids: list[str],
    failures_by_section: dict[str, list[dict[str, str]]],
    sections: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """Build ``qc_section_failures`` bundles for section patch prompts.

    Each bundle: ``section_id``, ``heading``, ``current_section_json``, ``failures``
    where each failure has ``check_id``, ``category``, ``evidence``, ``corrective_hint``.
    """
    bundles: list[dict[str, Any]] = []
    for section_id in failed_section_ids:
        section = sections.get(section_id, {})
        bundles.append(
            {
                "section_id": section_id,
                "heading": str(section.get("heading", "")),
                "current_section_json": section,
                "failures": failures_by_section.get(section_id, []),
            }
        )
    return bundles


def classify_retry_routing(
    qc_result: dict[str, Any],
    document: dict[str, Any],
    checklist: list[dict[str, Any]] | None = None,
    *,
    topic_split: list[dict[str, Any]] | None = None,
    structure_missing_ids: set[str] | frozenset[str] | None = None,
) -> RetryRoutingResult:
    """Map QC failures to retry mode and per-section rework targets.

    Args:
        qc_result: Output of ``build_final_qc_result`` (checks + failed_checks).
        document: Parsed study document under evaluation.
        checklist: ``must_cover_checklist`` for id normalization and insert mapping.
        topic_split: Blueprint section ids (``ts_*``) for structure enrichment.
        structure_missing_ids: Precomputed missing section ids from QC node
            (avoids redundant ``validate_section_id_coverage`` when provided).

    Returns:
        ``RetryRoutingResult`` with mode, failed/missing ids, ``section_failures``
        bundles (category + evidence + corrective_hint per section), and rationale.
    """
    checklist = checklist or []
    failed = _failed_checks(qc_result)
    raw_checks = qc_result.get("checks")
    checks: list[dict[str, Any]] = (
        [c for c in raw_checks if isinstance(c, dict)]
        if isinstance(raw_checks, list)
        else failed
    )

    failure_class = classify_failure_class(failed)

    raw_recommendation = qc_result.get("retry_recommendation")
    recommendation_dict = sanitize_retry_recommendation(
        raw_recommendation if isinstance(raw_recommendation, dict) else None,
        checks=[c for c in checks if isinstance(c, dict)],
        document=document,
        checklist=checklist,
    )
    # Prefer sanitized copy for downstream rationale / consumers of this dict.
    if recommendation_dict is not None:
        qc_result = {**qc_result, "retry_recommendation": recommendation_dict}

    llm_recommendation_mode: RetryMode | None = None
    llm_recommendation_rationale = ""
    if recommendation_dict is not None:
        llm_recommendation_mode = _coerce_llm_recommendation_mode(
            recommendation_dict.get("mode")
        )
        llm_recommendation_rationale = str(
            recommendation_dict.get("rationale", "")
        ).strip()

    if not failed:
        # All checks passed. After sanitization the recommendation should be
        # mode=none; if actionable targets remain, honor that mode instead of
        # returning none while qc_passed is false (Calvin full-regen bug).
        failed_section_ids: set[str] = set()
        missing_checklist_ids: set[str] = set()
        failures_by_section: dict[str, list[dict[str, str]]] = {}
        _merge_llm_recommendation_targets(
            recommendation=recommendation_dict,
            document=document,
            checklist=checklist,
            failed_section_ids=failed_section_ids,
            missing_checklist_ids=missing_checklist_ids,
            failures_by_section=failures_by_section,
            failed=failed,
        )
        if not failed_section_ids and not missing_checklist_ids:
            return RetryRoutingResult(
                mode="none",
                failed_section_ids=[],
                missing_checklist_ids=[],
                section_failures=[],
                rationale="no failed checks",
                failure_class=failure_class,
            )

        deterministic = _deterministic_mode(
            failed_section_ids=failed_section_ids,
            missing_checklist_ids=missing_checklist_ids,
        )
        mode = _reconcile_mode(
            deterministic=deterministic,
            llm_recommendation_mode=llm_recommendation_mode,
            force_full_regen=False,
            failed_section_ids=failed_section_ids,
            missing_checklist_ids=missing_checklist_ids,
            teaching_alignment_sole_failure=False,
        )
        sorted_failed_ids = sorted(failed_section_ids)
        sorted_missing_ids = sorted(missing_checklist_ids)
        section_failures = _build_section_failures(
            sorted_failed_ids,
            failures_by_section,
            _section_by_id(document),
        )
        placement_section_failures, substance_section_failures = (
            split_section_failures_by_kind(section_failures)
        )
        rationale = (
            llm_recommendation_rationale
            if llm_recommendation_rationale and llm_recommendation_mode == mode
            else f"honored retry_recommendation with no failed checks: {mode}"
        )
        return RetryRoutingResult(
            mode=mode,
            failed_section_ids=sorted_failed_ids,
            missing_checklist_ids=sorted_missing_ids,
            section_failures=section_failures,
            placement_section_failures=placement_section_failures,
            substance_section_failures=substance_section_failures,
            rationale=rationale,
            failure_class=failure_class,
        )

    (
        failed_section_ids,
        missing_checklist_ids,
        failures_by_section,
        unmapped_count,
        structure_missing,
    ) = _map_failures_to_targets(
        failed,
        document=document,
        checklist=checklist,
        topic_split=topic_split,
        structure_missing_ids=structure_missing_ids,
    )

    _merge_llm_recommendation_targets(
        recommendation=recommendation_dict,
        document=document,
        checklist=checklist,
        failed_section_ids=failed_section_ids,
        missing_checklist_ids=missing_checklist_ids,
        failures_by_section=failures_by_section,
        failed=failed,
    )

    force_full_regen, force_reason = _should_force_full_regeneration(
        failed=failed,
        failed_section_ids=failed_section_ids,
        missing_checklist_ids=missing_checklist_ids,
        checklist=checklist,
        topic_split=topic_split,
        unmapped_count=unmapped_count,
        structure_missing=structure_missing,
    )

    deterministic = _deterministic_mode(
        failed_section_ids=failed_section_ids,
        missing_checklist_ids=missing_checklist_ids,
    )

    teaching_alignment_only = _teaching_alignment_sole_failure(failed)

    mode = _reconcile_mode(
        deterministic=deterministic,
        llm_recommendation_mode=llm_recommendation_mode,
        force_full_regen=force_full_regen,
        failed_section_ids=failed_section_ids,
        missing_checklist_ids=missing_checklist_ids,
        teaching_alignment_sole_failure=teaching_alignment_only,
    )

    if is_placement_only_failure(failed) and mode == "full_regeneration":
        mode = "section_patch"

    if (
        _is_structure_only_failure(failed)
        and missing_checklist_ids
        and not force_full_regen
    ):
        mode = "section_insert"
        rationale = "deterministic routing: section_insert (missing section ids)"
    elif force_full_regen:
        rationale = force_reason
    elif teaching_alignment_only and mode == "full_regeneration":
        rationale = "teaching_alignment is the sole unresolved failure"
    elif llm_recommendation_rationale and llm_recommendation_mode == mode:
        rationale = llm_recommendation_rationale
    elif mode == deterministic:
        rationale = f"deterministic routing: {mode}"
    else:
        rationale = f"deterministic {deterministic} reconciled to {mode}"

    sorted_failed_ids = sorted(failed_section_ids)
    sorted_missing_ids = sorted(missing_checklist_ids)
    sections = _section_by_id(document)
    section_failures = _build_section_failures(
        sorted_failed_ids,
        failures_by_section,
        sections,
    )
    placement_section_failures, substance_section_failures = (
        split_section_failures_by_kind(section_failures)
    )

    return RetryRoutingResult(
        mode=mode,
        failed_section_ids=sorted_failed_ids,
        missing_checklist_ids=sorted_missing_ids,
        section_failures=section_failures,
        placement_section_failures=placement_section_failures,
        substance_section_failures=substance_section_failures,
        rationale=rationale,
        failure_class=failure_class,
    )
