"""Frozen check/section sets for incremental QC on retries."""

from __future__ import annotations

from typing import Any

from src.api.utils.study_agent_utils.quality_check_utils.core.constants import (
    FROZEN_SECTION_CATEGORIES,
)


def accumulate_frozen_sets(
    checks: list[dict[str, Any]],
    existing_check_ids: list[str] | None,
    existing_section_ids: list[str] | None,
) -> tuple[list[str], list[str]]:
    """Merge passed checks into frozen sets so retry QC skips re-evaluating them."""
    frozen_ids = set(existing_check_ids or [])
    frozen_section_ids = set(existing_section_ids or [])

    for check in checks:
        if not check.get("passed", True):
            continue
        category = check.get("category", "")
        if category == "must_cover":
            checklist_id = str(check.get("checklist_id", "")).strip()
            if checklist_id:
                frozen_ids.add(checklist_id)
        elif category in FROZEN_SECTION_CATEGORIES:
            section_id = str(check.get("section_id", "")).strip()
            if section_id:
                frozen_section_ids.add(section_id)

    return sorted(frozen_ids), sorted(frozen_section_ids)
