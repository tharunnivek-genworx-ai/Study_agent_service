"""Phase 1b: deterministic placement remediation shared by QC node and test runner."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from src.api.utils.study_agent_utils.generation.study_generation_json import (
    canonicalize_generation_json,
)
from src.api.utils.study_agent_utils.quality_check_utils.checks.block_placement_checks import (
    block_placement_checks,
)
from src.api.utils.study_agent_utils.quality_check_utils.core.failure_class import (
    is_placement_check,
)
from src.api.utils.study_agent_utils.quality_check_utils.remediation.relocation_apply import (
    apply_relocation_plans,
)
from src.api.utils.study_agent_utils.quality_check_utils.remediation.relocation_plan import (
    build_relocation_plans,
)
from src.api.utils.study_agent_utils.quality_check_utils.remediation.relocation_types import (
    RelocationPlan,
    RemediationReport,
)


@dataclass
class PlacementRemediationResult:
    document: dict[str, Any]
    generated_content: str
    block_placement_failures: list[dict[str, Any]]
    structure_checks: list[dict[str, Any]]
    qc_relocation_plans: list[dict[str, Any]] | None
    remediation_report: RemediationReport | None
    document_patched: bool


def relocation_plans_for_llm_fallback(
    relocation_plans: list[RelocationPlan],
    *,
    needs_llm_fallback: bool,
    remaining_placement_failures: list[dict[str, Any]],
) -> list[dict[str, Any]] | None:
    """Build state payload for placement-only LLM relocate prompt."""
    if not needs_llm_fallback and not remaining_placement_failures:
        return None

    remaining_section_ids = {
        str(check.get("section_id", "")).strip()
        for check in remaining_placement_failures
        if str(check.get("section_id", "")).strip()
    }
    plan_dicts: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()

    for plan in relocation_plans:
        key = (plan.check_id, plan.section_id)
        if plan.has_low_confidence or plan.section_id in remaining_section_ids:
            if key not in seen:
                seen.add(key)
                plan_dicts.append(plan.to_dict())

    for check in remaining_placement_failures:
        check_id = str(check.get("id", "")).strip()
        section_id = str(check.get("section_id", "")).strip()
        key = (check_id, section_id)
        if not section_id or key in seen:
            continue
        seen.add(key)
        embedded = check.get("relocation_plan")
        relocations: list[dict[str, Any]] = []
        if isinstance(embedded, dict):
            relocations = list(embedded.get("relocations") or [])
        plan_dicts.append(
            {
                "check_id": check_id,
                "section_id": section_id,
                "relocations": relocations,
                "has_low_confidence": True,
            }
        )

    return plan_dicts or None


def run_placement_remediation_phase(
    document: dict[str, Any],
    *,
    domain: str,
    checklist: list[dict[str, Any]] | None,
    optional_structure_check: dict[str, Any] | None,
    generated_content: str,
) -> PlacementRemediationResult:
    """Run build/apply relocation plans and re-verify placement checks."""
    block_placement_failures = block_placement_checks(
        document,
        domain=domain,
        checklist=checklist,
    )
    structure_checks: list[dict[str, Any]] = []
    if optional_structure_check:
        structure_checks.append(optional_structure_check)
    structure_checks.extend(block_placement_failures)

    placement_failures = [c for c in block_placement_failures if is_placement_check(c)]
    if not placement_failures:
        return PlacementRemediationResult(
            document=document,
            generated_content=generated_content,
            block_placement_failures=block_placement_failures,
            structure_checks=structure_checks,
            qc_relocation_plans=None,
            remediation_report=None,
            document_patched=False,
        )

    relocation_plans = build_relocation_plans(
        document,
        placement_failures,
        domain=domain,
    )
    patched_doc, remediation_report = apply_relocation_plans(
        document,
        relocation_plans,
    )

    document_patched = False
    if remediation_report.fixed_section_ids:
        document = patched_doc
        generated_content = canonicalize_generation_json(json.dumps(document))
        document_patched = True
        block_placement_failures = block_placement_checks(
            document,
            domain=domain,
            checklist=checklist,
        )
        structure_checks = []
        if optional_structure_check:
            structure_checks.append(optional_structure_check)
        structure_checks.extend(block_placement_failures)
        remediation_report = RemediationReport(
            fixed_section_ids=remediation_report.fixed_section_ids,
            all_resolved=not block_placement_failures,
            needs_llm_fallback=remediation_report.needs_llm_fallback
            or bool(block_placement_failures),
            applied_plans=remediation_report.applied_plans,
            skipped_low_confidence=remediation_report.skipped_low_confidence,
        )

    remaining_placement = [c for c in block_placement_failures if is_placement_check(c)]
    qc_relocation_plans = relocation_plans_for_llm_fallback(
        relocation_plans,
        needs_llm_fallback=remediation_report.needs_llm_fallback,
        remaining_placement_failures=remaining_placement,
    )

    return PlacementRemediationResult(
        document=document,
        generated_content=generated_content,
        block_placement_failures=block_placement_failures,
        structure_checks=structure_checks,
        qc_relocation_plans=qc_relocation_plans,
        remediation_report=remediation_report,
        document_patched=document_patched,
    )
