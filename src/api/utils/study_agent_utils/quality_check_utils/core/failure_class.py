"""Failure-class taxonomy for QC routing and verification strategy."""

from __future__ import annotations

from typing import Any

from src.api.schemas.qc_schemas.qc_retry_routing_schema import FailureClass
from src.api.utils.study_agent_utils.generation.study_generation_json import (
    normalize_checklist_id,
)

PLACEMENT_CHECK_IDS = frozenset(
    {
        "det_equation_in_content",
        "det_math_in_code_block",
        "det_pseudocode_in_code_block",
        "det_code_in_formula_block",
        "det_empty_block_explanation",
        "det_conceptual_has_blocks",
    }
)

SUBSTANCE_CHECK_IDS = frozenset(
    {
        "det_stem_derivation_missing_formula",
        "det_stem_code_substitutes_derivation",
        "det_structure_coverage",
    }
)


def is_placement_check(check: dict[str, Any]) -> bool:
    return str(check.get("id", "")) in PLACEMENT_CHECK_IDS


def is_placement_only_failure(failed: list[dict[str, Any]]) -> bool:
    if not failed:
        return False
    return all(is_placement_check(check) for check in failed)


def _failure_check_id(check: dict[str, Any]) -> str:
    return str(check.get("check_id") or check.get("id") or "").strip()


def section_has_only_placement_failures(failures: list[dict[str, Any]]) -> bool:
    """True when every failure in a section bundle is a placement det_* check."""
    if not failures:
        return False
    return all(_failure_check_id(check) in PLACEMENT_CHECK_IDS for check in failures)


def split_section_failures_by_kind(
    section_failures: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Partition section bundles into placement-only vs substance/mixed."""
    placement: list[dict[str, Any]] = []
    substance: list[dict[str, Any]] = []
    for bundle in section_failures:
        if not isinstance(bundle, dict):
            continue
        failures = list(bundle.get("failures") or [])
        if section_has_only_placement_failures(failures):
            placement.append(bundle)
        else:
            substance.append(bundle)
    return placement, substance


def classify_failure_class(failed: list[dict[str, Any]]) -> FailureClass:
    if not failed:
        return "none"
    has_placement = any(is_placement_check(check) for check in failed)
    has_non_placement = any(not is_placement_check(check) for check in failed)
    if has_placement and has_non_placement:
        return "mixed"
    if has_placement:
        return "placement_only"
    return "substance"


def failed_must_cover_checklist_ids(
    failed: list[dict[str, Any]],
    checklist: list[dict[str, Any]],
) -> set[str]:
    """Checklist ids for must_cover checks that actually failed."""
    ids: set[str] = set()
    for check in failed:
        if str(check.get("category", "")) != "must_cover":
            continue
        if check.get("passed", True):
            continue
        item_id = normalize_checklist_id(
            str(check.get("checklist_id") or check.get("id", "")),
            checklist,
        )
        if item_id:
            ids.add(item_id)
    return ids
