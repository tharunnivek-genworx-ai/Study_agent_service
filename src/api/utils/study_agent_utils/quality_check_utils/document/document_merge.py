# src/api/utils/study_agent_utils/qc/document_merge.py
"""Merge study document sections after QC-driven generator retries.

Used by ``run_section_retry`` (patch/insert) and ``study_agent_node`` (full regen
preserve-passing merge). All merges are **section-level** — entire section dicts
are replaced or inserted; there is no line-level or subsection-level merge.

Key functions:
  - ``merge_section_patches``: swap failed sections with LLM patch output
  - ``insert_sections``: add missing blueprint/checklist sections
  - ``extract_sections_by_ids``: pull section JSON for ``<sections_to_fix>`` prompts
  - ``merge_full_regeneration_preserving_passing``: splice new + old sections after full regen
  - ``build_document_outline``: compact id/heading list for rework prompts
"""

from __future__ import annotations

import copy
import logging
import re
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

_CHECKLIST_ID_RE = re.compile(r"^mc_(\d+)$", re.IGNORECASE)


@dataclass
class MergePatchesResult:
    document: dict[str, Any]
    unmatched_patch_ids: list[str] = field(default_factory=list)


def _checklist_order(section_id: str) -> int | None:
    match = _CHECKLIST_ID_RE.match(str(section_id).strip())
    if not match:
        return None
    return int(match.group(1))


def _section_id(section: dict[str, Any]) -> str:
    raw = section.get("id")
    if raw is None:
        return ""
    return str(raw).strip()


def merge_section_patches(
    document: dict[str, Any], patches: list[dict[str, Any]]
) -> MergePatchesResult:
    """Replace whole sections in *document* whose ``id`` matches a patch section.

    Each patch from the section-rework LLM replaces the entire section dict at
    that index (content, formula_blocks, subsections, etc.). Valid content in
    other sections is untouched. Valid subsections *within* a patched section
    are not mechanically preserved — only LLM instruction-following.

    Args:
        document: Current full study document.
        patches: Section dicts from ``run_section_retry`` LLM output.

    Returns:
        ``MergePatchesResult`` with merged document and any patch ids not found.
    """
    merged = copy.deepcopy(document)
    sections: list[dict[str, Any]] = list(merged.get("sections") or [])
    index_by_id = {
        _section_id(section): index
        for index, section in enumerate(sections)
        if isinstance(section, dict) and _section_id(section)
    }

    unmatched: list[str] = []
    for patch in patches:
        if not isinstance(patch, dict):
            continue
        patch_id = _section_id(patch)
        if not patch_id:
            continue
        if patch_id in index_by_id:
            sections[index_by_id[patch_id]] = copy.deepcopy(patch)
        else:
            unmatched.append(patch_id)
            logger.warning("Section patch id %s not found in document", patch_id)

    merged["sections"] = sections
    return MergePatchesResult(document=merged, unmatched_patch_ids=unmatched)


def _default_insert_index(sections: list[dict[str, Any]], new_section_id: str) -> int:
    """Insert after the last section with a lower checklist order, else append."""
    new_order = _checklist_order(new_section_id)
    if new_order is None:
        return len(sections)

    best_index = -1
    best_order = -1
    for index, section in enumerate(sections):
        if not isinstance(section, dict):
            continue
        order = _checklist_order(_section_id(section))
        if order is not None and order < new_order and order > best_order:
            best_order = order
            best_index = index

    if best_index >= 0:
        return best_index + 1
    return len(sections)


def insert_sections(
    document: dict[str, Any],
    new_sections: list[dict[str, Any]],
    *,
    after_section_id: str | None = None,
) -> dict[str, Any]:
    """Insert *new_sections* into *document*, preserving checklist order by default."""
    merged = copy.deepcopy(document)
    sections: list[dict[str, Any]] = list(merged.get("sections") or [])

    ordered_new = sorted(
        [section for section in new_sections if isinstance(section, dict)],
        key=lambda section: _checklist_order(_section_id(section)) or 10**9,
    )

    for new_section in ordered_new:
        new_id = _section_id(new_section)
        if not new_id:
            sections.append(copy.deepcopy(new_section))
            continue

        if any(_section_id(existing) == new_id for existing in sections):
            logger.warning("Section id %s already exists — skipping insert", new_id)
            continue

        if after_section_id:
            anchor = str(after_section_id).strip()
            insert_at = next(
                (
                    index + 1
                    for index, section in enumerate(sections)
                    if _section_id(section) == anchor
                ),
                len(sections),
            )
        else:
            insert_at = _default_insert_index(sections, new_id)

        sections.insert(insert_at, copy.deepcopy(new_section))

    merged["sections"] = sections
    return merged


def extract_sections_by_ids(
    document: dict[str, Any], ids: list[str]
) -> list[dict[str, Any]]:
    """Return deep copies of sections whose ``id`` is in *ids*, in *ids* order.

    Used by ``section_rework_prompt.build_sections_to_fix_block`` to embed
    ``current_section_json`` for each failed section. Order follows the
    ``section_failures`` bundle order, not document order.

    Unknown ids are skipped silently (no error).
    """
    wanted = {str(section_id).strip() for section_id in ids if str(section_id).strip()}
    if not wanted:
        return []

    by_id = {
        _section_id(section): copy.deepcopy(section)
        for section in document.get("sections") or []
        if isinstance(section, dict) and _section_id(section)
    }
    ordered: list[dict[str, Any]] = []
    for raw_id in ids:
        normalized = str(raw_id).strip()
        if normalized in by_id:
            ordered.append(by_id[normalized])
    return ordered


def _ordered_section_ids(
    new_document: dict[str, Any],
    previous_document: dict[str, Any],
    *,
    topic_split: list[dict[str, Any]] | None = None,
) -> list[str]:
    """Build a stable section id order for full-regeneration merges."""
    if topic_split:
        blueprint_ids = [
            str(entry.get("id", "")).strip()
            for entry in topic_split
            if isinstance(entry, dict) and str(entry.get("id", "")).strip()
        ]
        if blueprint_ids:
            seen: set[str] = set()
            ordered: list[str] = []
            for section_id in blueprint_ids:
                if section_id not in seen:
                    seen.add(section_id)
                    ordered.append(section_id)
            for document in (previous_document, new_document):
                for section in document.get("sections") or []:
                    if not isinstance(section, dict):
                        continue
                    section_id = _section_id(section)
                    if section_id and section_id not in seen:
                        seen.add(section_id)
                        ordered.append(section_id)
            return ordered

    fallback_ordered: list[str] = []
    fallback_seen: set[str] = set()
    for document in (previous_document, new_document):
        for section in document.get("sections") or []:
            if not isinstance(section, dict):
                continue
            section_id = _section_id(section)
            if section_id and section_id not in fallback_seen:
                fallback_seen.add(section_id)
                fallback_ordered.append(section_id)
    return fallback_ordered


def merge_full_regeneration_preserving_passing(
    new_document: dict[str, Any],
    previous_document: dict[str, Any],
    *,
    rewrite_section_ids: set[str] | frozenset[str],
    topic_split: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """After full regen LLM output, keep passing sections from the previous draft.

    For each section id in blueprint order:
    - id in ``rewrite_section_ids`` → take from *new_document* (QC-failed sections)
    - else → prefer *previous_document* (passing sections preserved)

    Section bytes change only for rewrite ids — P3 hash gate drops stale frozen
    skips for changed sections while keeping frozen ids for preserved sections.

    Args:
        new_document: Full document JSON from full-regeneration LLM.
        previous_document: Document before regen (failed QC draft).
        rewrite_section_ids: ``qc_reverify_section_ids`` from routing.
        topic_split: Optional ordering blueprint for merged section list.
    """
    rewrite_ids = {
        str(section_id).strip()
        for section_id in rewrite_section_ids
        if str(section_id).strip()
    }
    previous_by_id = {
        _section_id(section): copy.deepcopy(section)
        for section in previous_document.get("sections") or []
        if isinstance(section, dict) and _section_id(section)
    }
    new_by_id = {
        _section_id(section): copy.deepcopy(section)
        for section in new_document.get("sections") or []
        if isinstance(section, dict) and _section_id(section)
    }

    merged_sections: list[dict[str, Any]] = []
    for section_id in _ordered_section_ids(
        new_document, previous_document, topic_split=topic_split
    ):
        if section_id in rewrite_ids:
            section = new_by_id.get(section_id) or previous_by_id.get(section_id)
        else:
            section = previous_by_id.get(section_id) or new_by_id.get(section_id)
        if section is not None:
            merged_sections.append(section)

    merged_ids = {_section_id(section) for section in merged_sections}
    for section_id, section in new_by_id.items():
        if section_id not in merged_ids:
            merged_sections.append(section)
            merged_ids.add(section_id)

    return {**copy.deepcopy(new_document), "sections": merged_sections}


def build_document_outline(document: dict[str, Any]) -> str:
    """Return a compact outline of section headings and ids."""
    lines: list[str] = []
    for section in document.get("sections") or []:
        if not isinstance(section, dict):
            continue
        section_id = _section_id(section)
        heading = str(section.get("heading", "")).strip()
        if section_id and heading:
            lines.append(f"- [{section_id}] {heading}")
        elif section_id:
            lines.append(f"- [{section_id}]")
        elif heading:
            lines.append(f"- {heading}")
    return "\n".join(lines)
