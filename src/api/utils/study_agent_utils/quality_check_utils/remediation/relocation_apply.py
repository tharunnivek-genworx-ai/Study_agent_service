"""Apply relocation plans to a study document."""

from __future__ import annotations

import copy
from typing import Any

from src.api.utils.study_agent_utils.quality_check_utils.remediation.placement_patterns import (
    equation_text_for_formula_block,
)
from src.api.utils.study_agent_utils.quality_check_utils.remediation.relocation_types import (
    Relocation,
    RelocationPlan,
    RemediationReport,
)


def apply_relocation_plans(
    document: dict[str, Any],
    plans: list[RelocationPlan],
    *,
    only_high_confidence: bool = True,
) -> tuple[dict[str, Any], RemediationReport]:
    """Apply relocation plans to a deep-copied document."""
    patched = copy.deepcopy(document)
    section_by_id = {
        str(section.get("id", "")).strip(): section
        for section in patched.get("sections") or []
        if isinstance(section, dict) and str(section.get("id", "")).strip()
    }

    fixed_section_ids: list[str] = []
    applied_plans: list[RelocationPlan] = []
    skipped_low_confidence = 0
    needs_llm_fallback = False

    for plan in plans:
        section = section_by_id.get(plan.section_id)
        if section is None:
            needs_llm_fallback = True
            continue

        section_changed = False
        applied_relocations: list[Relocation] = []
        for relocation in plan.relocations:
            if only_high_confidence and relocation.confidence == "low":
                skipped_low_confidence += 1
                needs_llm_fallback = True
                continue
            if _apply_relocation(section, relocation):
                section_changed = True
                applied_relocations.append(relocation)
            else:
                needs_llm_fallback = True

        if applied_relocations:
            applied_plans.append(
                RelocationPlan(
                    check_id=plan.check_id,
                    section_id=plan.section_id,
                    relocations=applied_relocations,
                )
            )
        if section_changed and plan.section_id not in fixed_section_ids:
            fixed_section_ids.append(plan.section_id)

    if any(plan.has_low_confidence for plan in plans):
        needs_llm_fallback = needs_llm_fallback or any(
            plan.has_low_confidence for plan in plans
        )

    if not plans:
        all_resolved = not needs_llm_fallback
    else:
        all_resolved = (
            not needs_llm_fallback
            and skipped_low_confidence == 0
            and bool(applied_plans)
        )

    return patched, RemediationReport(
        fixed_section_ids=fixed_section_ids,
        all_resolved=all_resolved,
        needs_llm_fallback=needs_llm_fallback,
        applied_plans=applied_plans,
        skipped_low_confidence=skipped_low_confidence,
    )


def _container_for_relocation(
    section: dict[str, Any],
    relocation: Relocation,
) -> dict[str, Any] | None:
    if relocation.subsection_heading:
        for subsection in section.get("subsections") or []:
            if not isinstance(subsection, dict):
                continue
            heading = str(subsection.get("heading", "")).strip()
            if heading == relocation.subsection_heading:
                return subsection
        return None
    return section


def _apply_relocation(section: dict[str, Any], relocation: Relocation) -> bool:
    action = relocation.action
    if action == "extract":
        return _apply_extract(section, relocation)
    if action == "dereference":
        return _apply_dereference(section, relocation)
    if action == "move_block":
        return _apply_move_block(section, relocation)
    if action == "fill_explanation":
        return _apply_fill_explanation(section, relocation)
    return False


def _apply_extract(section: dict[str, Any], relocation: Relocation) -> bool:
    container = _container_for_relocation(section, relocation)
    if container is None:
        return False
    content = str(container.get("content", ""))
    start = relocation.span_start
    end = relocation.span_end
    span_text = relocation.span_text
    if start is None or end is None or not span_text:
        return False
    if content[start:end].strip() != span_text.strip():
        return False

    new_content = f"{content[:start].rstrip()} {content[end:].lstrip()}".strip()
    container["content"] = new_content
    formula_blocks = list(container.get("formula_blocks") or [])
    formula_blocks.append(
        {
            "notation": "LaTeX",
            "formula": equation_text_for_formula_block(span_text.strip()),
            "explanation": (
                "Equation relocated from prose; content otherwise unchanged."
            ),
        }
    )
    container["formula_blocks"] = formula_blocks
    return True


def _apply_dereference(section: dict[str, Any], relocation: Relocation) -> bool:
    container = _container_for_relocation(section, relocation)
    if container is None:
        return False
    content = str(container.get("content", ""))
    start = relocation.span_start
    end = relocation.span_end
    replacement = relocation.replacement
    if start is None or end is None or replacement is None:
        return False

    container["content"] = f"{content[:start]}{replacement}{content[end:]}"
    return True


def _apply_move_block(section: dict[str, Any], relocation: Relocation) -> bool:
    container = _container_for_relocation(section, relocation)
    if container is None:
        return False
    source_kind = relocation.block_kind
    target_kind = relocation.target_kind
    index = relocation.block_index
    if source_kind is None or target_kind is None or index is None:
        return False

    source_blocks = list(container.get(source_kind) or [])
    if index < 0 or index >= len(source_blocks):
        return False

    block = source_blocks.pop(index)
    target_blocks = list(container.get(target_kind) or [])

    if source_kind == "code_blocks" and target_kind == "formula_blocks":
        target_blocks.append(
            {
                "notation": str(block.get("language", "plain-text")),
                "formula": str(block.get("code", "")),
                "explanation": str(block.get("explanation", "")).strip()
                or "Notation relocated from code_blocks.",
            }
        )
    elif source_kind == "formula_blocks" and target_kind == "code_blocks":
        target_blocks.append(
            {
                "language": "python",
                "code": str(block.get("formula", "")),
                "explanation": str(block.get("explanation", "")).strip()
                or "Code relocated from formula_blocks.",
            }
        )
    else:
        return False

    container[source_kind] = source_blocks
    container[target_kind] = target_blocks
    return True


def _apply_fill_explanation(section: dict[str, Any], relocation: Relocation) -> bool:
    container = _container_for_relocation(section, relocation)
    if container is None:
        return False
    block_kind = relocation.block_kind
    index = relocation.block_index
    explanation = relocation.explanation
    if block_kind is None or index is None or not explanation:
        return False

    blocks = list(container.get(block_kind) or [])
    if index < 0 or index >= len(blocks):
        return False
    block = dict(blocks[index])
    if str(block.get("explanation", "")).strip():
        return False
    block["explanation"] = explanation
    blocks[index] = block
    container[block_kind] = blocks
    return True
