"""Frozen QC sets and section content lineage (P3/P4).

Pipeline role
--------------
After a QC pass, some checks **passed** and need not be re-run on the next
**full** verification pass. This module tracks those passes as *frozen ids*:

- ``must_cover`` (passed) → ``qc_frozen_check_ids`` (checklist ids ``mc_*``)
- ``code_quality`` / ``stack_fidelity`` (passed) → ``qc_frozen_section_keys`` (section ids)

Frozen ids alone are **not** sufficient: section content can change via patch,
insert, or full regen while the id stays the same. P3/P4 adds
``qc_section_content_hashes``: a SHA-256 baseline per section id captured at QC
exit. Before a full QC pass, ``effective_frozen_sets`` / ``resolve_frozen_for_full_qc``
only honor frozen ids whose section hash still matches the baseline.

Public entry points (used by ``quality_check_node`` and test ``qc_runner``):

- **Full QC entry:** ``resolve_frozen_for_full_qc`` — hash-gate stale frozen ids
- **QC exit (full or targeted):** ``refresh_frozen_lineage_after_qc`` — prune
  touched sections (targeted), accumulate new passes, refresh baselines

Not frozen: ``content_accuracy``, ``document_coherence``, ``teaching_alignment``.
Those use ``targeted_merge`` on pass 2 or full re-check on pass 1.

See also: ``FULL_REGEN_FROZEN_SETS_EDGE_CASES.txt``, P3/P4 plan.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from src.api.utils.study_agent_utils.generation.must_cover_checklist_format import (
    checklist_section_id,
)
from src.api.utils.study_agent_utils.generation.study_generation_json import (
    resolve_checklist_section_id,
)
from src.api.utils.study_agent_utils.quality_check_utils.core.constants import (
    FROZEN_SECTION_CATEGORIES,
)


def hash_section(section: dict[str, Any]) -> str:
    """Compute a stable SHA-256 digest of one section dict.

    Uses sorted-key JSON so field order in the LLM output does not affect the
    hash. Any change to content, blocks, or subsections changes the digest.

    Args:
        section: One element from ``document["sections"]``.

    Returns:
        Hex-encoded SHA-256 string used as the lineage baseline for that section id.
    """
    canonical = json.dumps(
        section, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def build_section_hashes(document: dict[str, Any]) -> dict[str, str]:
    """Build a map of section id → content hash for the whole document.

    Called at QC exit to persist ``qc_section_content_hashes`` in graph state
    and DB. Used at full QC entry to validate frozen ids.

    Args:
        document: Parsed study document with a ``sections`` array.

    Returns:
        Dict keyed by section id (e.g. ``ts_1``, ``mc_2``). Sections without
        an id are skipped.
    """
    sections = document.get("sections") or []
    hashes: dict[str, str] = {}
    for section in sections:
        section_id = str(section.get("id", "")).strip()
        if section_id:
            hashes[section_id] = hash_section(section)
    return hashes


def _checklist_ids_for_sections(
    checklist: list[dict[str, Any]],
    section_ids: set[str],
) -> set[str]:
    """Map document section ids to their ``must_cover`` checklist ids.

    Used when pruning frozen checklist ids for sections that were patched or
    re-verified on a targeted QC pass.

    Args:
        checklist: ``must_cover_checklist`` from graph state.
        section_ids: Document section ids touched by patch/insert/reverify.

    Returns:
        Set of ``mc_*`` ids whose canonical ``section_id`` is in ``section_ids``.
    """
    result: set[str] = set()
    for item in checklist:
        item_id = str(item.get("id", "")).strip()
        if not item_id:
            continue
        if checklist_section_id(item) in section_ids:
            result.add(item_id)
    return result


def prune_frozen_for_sections(
    frozen_check_ids: list[str] | None,
    frozen_section_ids: list[str] | None,
    *,
    touched_section_ids: set[str] | list[str],
    checklist: list[dict[str, Any]] | None = None,
    reverify_checklist_ids: set[str] | list[str] | None = None,
) -> tuple[list[str], list[str]]:
    """Remove frozen ids for sections that were revised or re-verified.

    Runs at the start of ``refresh_frozen_lineage_after_qc`` on **targeted**
    QC passes when ``touched_section_ids`` is set (reverify list + inserted
    sections). Ensures a patched section's previously frozen ``mc_*`` or code
    section key is dropped before re-accumulating passes from the merged result.

    Args:
        frozen_check_ids: Current ``qc_frozen_check_ids`` from state.
        frozen_section_ids: Current ``qc_frozen_section_keys`` from state.
        touched_section_ids: Section ids in scope for targeted re-verify.
        checklist: Used to resolve ``mc_*`` → section id for checklist pruning.
        reverify_checklist_ids: Explicit missing checklist ids (insert targets).

    Returns:
        ``(pruned_check_ids, pruned_section_ids)`` sorted lists.
    """
    touched = {
        str(section_id).strip() for section_id in touched_section_ids if section_id
    }
    if not touched and not reverify_checklist_ids:
        return list(frozen_check_ids or []), list(frozen_section_ids or [])

    pruned_checklist_ids = {
        str(item_id).strip() for item_id in (reverify_checklist_ids or []) if item_id
    }
    if checklist:
        pruned_checklist_ids |= _checklist_ids_for_sections(checklist, touched)

    pruned_section_ids = set(frozen_section_ids or [])
    pruned_section_ids -= touched

    pruned_check_ids = [
        check_id
        for check_id in (frozen_check_ids or [])
        if str(check_id).strip() not in pruned_checklist_ids
    ]

    return sorted(pruned_check_ids), sorted(pruned_section_ids)


def _section_hash_valid(
    section_id: str,
    *,
    stored_hashes: dict[str, str],
    current_hashes: dict[str, str],
) -> bool:
    """True when *section_id* exists in both hash maps and digests match."""
    if not section_id:
        return False
    baseline = stored_hashes.get(section_id)
    if baseline is None:
        return False
    current = current_hashes.get(section_id)
    if current is None:
        return False
    return current == baseline


def effective_frozen_sets(
    *,
    frozen_check_ids: list[str] | None,
    frozen_section_ids: list[str] | None,
    stored_hashes: dict[str, str] | None,
    document: dict[str, Any],
    checklist: list[dict[str, Any]] | None = None,
) -> tuple[list[str], list[str]]:
    """Return frozen ids safe to skip on a full QC pass (hash gate).

    A frozen ``mc_*`` is kept only if the checklist item's section hash matches
    the baseline stored at the last QC exit. A frozen code section id is kept
    only if that section's hash matches.

    If ``stored_hashes`` is empty/None (legacy row or first attempt), returns
    ``([], [])`` so full QC evaluates everything — safe default.

    Used by:
    - ``quality_check_node`` before ``run_verification_pass``
    - ``study_material_service`` on DB resume (P4)

    Args:
        frozen_check_ids: Persisted ``qc_frozen_check_ids``.
        frozen_section_ids: Persisted ``qc_frozen_section_keys``.
        stored_hashes: Persisted ``qc_section_content_hashes`` baselines.
        document: Current document to hash and compare.
        checklist: Resolves ``mc_*`` → section id for checklist frozen ids.

    Returns:
        ``(valid_check_ids, valid_section_ids)`` to pass into the QC prompt.
    """
    if not stored_hashes:
        return [], []

    current_hashes = build_section_hashes(document)
    checklist = checklist or []

    valid_section_ids = sorted(
        section_id
        for section_id in (frozen_section_ids or [])
        if _section_hash_valid(
            str(section_id).strip(),
            stored_hashes=stored_hashes,
            current_hashes=current_hashes,
        )
    )

    valid_check_ids: list[str] = []
    for check_id in frozen_check_ids or []:
        normalized = str(check_id).strip()
        if not normalized:
            continue
        section_id = resolve_checklist_section_id(checklist, normalized)
        if _section_hash_valid(
            section_id,
            stored_hashes=stored_hashes,
            current_hashes=current_hashes,
        ):
            valid_check_ids.append(normalized)

    return sorted(valid_check_ids), valid_section_ids


def resolve_frozen_for_full_qc(
    *,
    frozen_check_ids: list[str] | None,
    frozen_section_ids: list[str] | None,
    stored_hashes: dict[str, str] | None,
    document: dict[str, Any],
    checklist: list[dict[str, Any]] | None = None,
) -> tuple[list[str], list[str]]:
    """Alias for ``effective_frozen_sets`` at full QC entry call sites.

    Never pass raw ``state.get("qc_frozen_*")`` directly to the LLM — always
    call this first so content changes invalidate stale skips.
    """
    return effective_frozen_sets(
        frozen_check_ids=frozen_check_ids,
        frozen_section_ids=frozen_section_ids,
        stored_hashes=stored_hashes,
        document=document,
        checklist=checklist,
    )


def refresh_frozen_lineage_after_qc(
    checks: list[dict[str, Any]],
    *,
    existing_check_ids: list[str] | None,
    existing_section_ids: list[str] | None,
    document: dict[str, Any],
    checklist: list[dict[str, Any]] | None = None,
    touched_section_ids: list[str] | None = None,
    reverify_checklist_ids: list[str] | None = None,
) -> tuple[list[str], list[str], dict[str, str]]:
    """Update frozen sets and section hash baselines after every QC pass.

    Pipeline steps:
    1. **Prune** (targeted only): drop frozen ids for ``touched_section_ids``.
    2. **Accumulate**: union newly passed ``must_cover`` / code checks.
    3. **Hash**: snapshot ``build_section_hashes(document)`` for next gate.

    Runs on both full and targeted QC exits (replaces legacy full-only
    ``accumulate_frozen_sets`` call).

    Args:
        checks: Final merged check list from ``build_final_qc_result``.
        existing_check_ids: Prior ``qc_frozen_check_ids``.
        existing_section_ids: Prior ``qc_frozen_section_keys``.
        document: Document that was just evaluated.
        checklist: ``must_cover_checklist`` for prune mapping.
        touched_section_ids: ``reverify_section_ids`` on targeted pass; None on full.
        reverify_checklist_ids: Missing checklist ids on targeted pass.

    Returns:
        ``(frozen_check_ids, frozen_section_ids, section_content_hashes)`` for
        ``base_qc_return``.
    """
    check_ids = existing_check_ids
    section_ids = existing_section_ids

    if touched_section_ids:
        check_ids, section_ids = prune_frozen_for_sections(
            check_ids,
            section_ids,
            touched_section_ids=touched_section_ids,
            checklist=checklist,
            reverify_checklist_ids=reverify_checklist_ids,
        )

    frozen_check_ids, frozen_section_ids = accumulate_frozen_sets(
        checks,
        check_ids,
        section_ids,
    )
    section_hashes = build_section_hashes(document)
    return frozen_check_ids, frozen_section_ids, section_hashes


def accumulate_frozen_sets(
    checks: list[dict[str, Any]],
    existing_check_ids: list[str] | None,
    existing_section_ids: list[str] | None,
) -> tuple[list[str], list[str]]:
    """Union newly **passed** checks into frozen id sets (internal primitive).

    Only passed checks contribute. Failed checks are handled by retry routing,
    not freezing.

    Categories:
    - ``must_cover`` → add ``checklist_id`` (``mc_*``)
    - ``code_quality`` / ``stack_fidelity`` → add ``section_id``

    Not accumulated: ``content_accuracy``, ``document_coherence``,
    ``teaching_alignment``, deterministic ``det_*`` (they use merge/routing).

    Prefer ``refresh_frozen_lineage_after_qc`` at QC node exit; this function
    is the low-level merge step inside that helper.

    Args:
        checks: QC check dicts (merged deterministic + LLM).
        existing_check_ids: Prior frozen checklist ids.
        existing_section_ids: Prior frozen code section ids.

    Returns:
        Sorted ``(frozen_check_ids, frozen_section_ids)``.
    """
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
