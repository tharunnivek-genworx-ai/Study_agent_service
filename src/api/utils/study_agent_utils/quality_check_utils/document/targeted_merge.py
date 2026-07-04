"""Merge targeted QC verification checks into a prior full QC result.

Pipeline role (pass 2 QC)
-------------------------
After ``study_agent`` patches sections, ``quality_check_node`` runs targeted
LLM verification on revised sections only. ``merge_targeted_qc_checks`` combines:

  - **Kept** checks from pass 1 for sections *outside* reverify scope
  - **New** checks from the targeted verification pass

Complements frozen-set lineage (id-level skip on full QC) and
``targeted_merge`` eviction rules (check-level replace on reverify).

``check_targets_reverify`` decides which prior checks are stale after a patch.
Deterministic ``det_*`` checks are re-run on the full merged document each QC
visit (not merged through this module).
"""

from __future__ import annotations

import logging
from typing import Any

from src.api.utils.study_agent_utils.generation.study_generation_json import (
    checklist_section_id,
    normalize_checklist_id,
    resolve_checklist_section_id,
)

logger = logging.getLogger(__name__)

# Categories whose checks are tied to a specific section and can be
# replaced once that section is re-verified.
_SECTION_SCOPED_CATEGORIES = frozenset(
    {"content_accuracy", "code_quality", "stack_fidelity", "document_coherence"}
)


def _reverify_section_ids(
    reverify_section_ids: list[str],
    reverify_checklist_ids: list[str] | None,
) -> set[str]:
    return {
        str(section_id).strip() for section_id in reverify_section_ids if section_id
    }


def _checklist_ids_for_sections(
    checklist: list[dict[str, Any]],
    section_ids: set[str],
) -> set[str]:
    """All must_cover checklist ids whose canonical section is in section_ids."""
    result: set[str] = set()
    for item in checklist:
        item_id = str(item.get("id", "")).strip()
        if not item_id:
            continue
        if checklist_section_id(item) in section_ids:
            result.add(item_id)
    return result


def _canonical_section_for_check(
    check: dict[str, Any],
    checklist: list[dict[str, Any]] | None,
) -> str:
    """Resolve section_id for a must_cover check via checklist when possible."""
    if not checklist:
        return ""
    if str(check.get("category", "")) != "must_cover":
        return ""
    raw = check.get("checklist_id") or check.get("id")
    if not raw:
        return ""
    checklist_id = normalize_checklist_id(str(raw), checklist)
    return resolve_checklist_section_id(checklist, checklist_id)


def _reverify_checklist_ids(
    reverify_section_ids: list[str],
    reverify_checklist_ids: list[str] | None,
    checklist: list[dict[str, Any]] | None = None,
) -> set[str]:
    ids = {
        str(item_id).strip() for item_id in (reverify_checklist_ids or []) if item_id
    }
    section_ids = _reverify_section_ids(reverify_section_ids, None)
    if checklist:
        ids |= _checklist_ids_for_sections(checklist, section_ids)
    return ids


def check_targets_reverify(
    check: dict[str, Any],
    *,
    reverify_section_ids: set[str],
    reverify_checklist_ids: set[str],
    checklist: list[dict[str, Any]] | None = None,
) -> bool:
    """Return True when a prior check should be replaced by targeted re-verification.

    A check is evicted when:
    - must_cover: its checklist_id or section_id is in the reverify scope.
    - content_accuracy / code_quality / stack_fidelity: its section_id is in scope.
    - document_coherence: its section_id is in scope, OR it has no section_id
      (document-wide) and any section was revised.
    - teaching_alignment: its section_id is in scope when present; document-level
      checks (no section_id) are kept until a new full verification pass runs.
    """
    category = str(check.get("category", ""))
    section_id = str(check.get("section_id", "") or "").strip()
    checklist_id = str(check.get("checklist_id", "") or "").strip()

    if category == "must_cover":
        if checklist_id and checklist_id in reverify_checklist_ids:
            return True
        if section_id and section_id in reverify_section_ids:
            return True
        canonical = _canonical_section_for_check(check, checklist)
        if canonical and canonical in reverify_section_ids:
            return True
        return False

    if category in _SECTION_SCOPED_CATEGORIES:
        if section_id and section_id in reverify_section_ids:
            return True
        # document_coherence with no section_id is document-wide — evict
        # whenever any section was revised so the new pass can re-assess it.
        if category == "document_coherence" and not section_id:
            return bool(reverify_section_ids)
        return False

    if category == "teaching_alignment":
        if section_id:
            return section_id in reverify_section_ids
        # Document-level teaching_alignment is stale after any section revision.
        return bool(reverify_section_ids)

    return False


def _dedup_key(check: dict[str, Any]) -> tuple[str, ...]:
    category = str(check.get("category", ""))
    if category == "must_cover":
        return (category, str(check.get("checklist_id", "") or ""))
    return (
        category,
        str(check.get("section_id", "") or ""),
        str(check.get("checklist_id", "") or ""),
    )


def _dedup_checks(checks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Remove stale duplicates — keep the last occurrence per dedup key.

    For must_cover, dedup by (category, checklist_id) so a stale failure at a
    wrong section_id does not survive alongside a fresh pass at the canonical
    section. New checks are appended after kept ones, so last-wins means the
    fresh result from the targeted pass always beats a stale kept check.
    """
    seen: dict[tuple[str, ...], int] = {}
    for i, check in enumerate(checks):
        seen[_dedup_key(check)] = i
    surviving = set(seen.values())
    return [check for i, check in enumerate(checks) if i in surviving]


def _log_scoped_must_cover_gaps(
    merged: list[dict[str, Any]],
    checklist: list[dict[str, Any]],
    reverify_checklist_ids: set[str],
) -> None:
    scoped = [
        item
        for item in checklist
        if str(item.get("id", "")).strip() in reverify_checklist_ids
    ]
    for item in scoped:
        item_id = str(item.get("id", "")).strip()
        if not any(
            str(c.get("category", "")) == "must_cover"
            and str(c.get("checklist_id", "") or "").strip() == item_id
            for c in merged
        ):
            logger.debug(
                "scoped must_cover %s absent after targeted merge",
                item_id,
            )


def merge_targeted_qc_checks(
    prior_qc_result: dict[str, Any],
    new_verification: dict[str, Any] | None,
    *,
    reverify_section_ids: list[str],
    reverify_checklist_ids: list[str] | None = None,
    checklist: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Keep prior checks outside the re-verify scope; replace scoped checks with new results.

    After combining kept + new checks, a dedup pass ensures that any check
    not evicted by ``check_targets_reverify`` but whose dedup key was also
    emitted by the new pass is replaced by the fresh result (last-wins semantics).
    """
    section_ids = _reverify_section_ids(reverify_section_ids, None)
    checklist_ids = _reverify_checklist_ids(
        reverify_section_ids, reverify_checklist_ids, checklist
    )

    prior_checks = [
        check
        for check in (prior_qc_result.get("checks") or [])
        if isinstance(check, dict)
    ]
    kept = [
        check
        for check in prior_checks
        if not check_targets_reverify(
            check,
            reverify_section_ids=section_ids,
            reverify_checklist_ids=checklist_ids,
            checklist=checklist,
        )
    ]

    new_checks = [
        check
        for check in ((new_verification or {}).get("checks") or [])
        if isinstance(check, dict)
    ]

    merged = _dedup_checks(kept + new_checks)

    if checklist:
        _log_scoped_must_cover_gaps(merged, checklist, checklist_ids)

    return merged
