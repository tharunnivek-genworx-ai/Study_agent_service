"""Build relocation plans from failed placement checks."""

from __future__ import annotations

import ast
import re
from collections.abc import Iterator
from typing import Any

from src.api.utils.study_agent_utils.generation.study_generation_json import (
    _is_math_like_language,
)
from src.api.utils.study_agent_utils.quality_check_utils.core.failure_class import (
    PLACEMENT_CHECK_IDS,
)
from src.api.utils.study_agent_utils.quality_check_utils.remediation.placement_patterns import (
    extract_equation_core,
    find_equation_spans,
    is_narrative_equation_clause,
    looks_like_programming_code_in_formula,
    normalize_math,
)
from src.api.utils.study_agent_utils.quality_check_utils.remediation.relocation_types import (
    Relocation,
    RelocationPlan,
)

_EVIDENCE_LOCATION_RE = re.compile(
    r"^Section (.+?)(?:, subsection (.+?))?: ",
    re.DOTALL,
)

_EMPTY_EXPLANATION_TEMPLATE = "Notation relocated from prose; content unchanged."


def build_relocation_plans(
    document: dict[str, Any],
    failed_checks: list[dict[str, Any]],
    *,
    domain: str,
) -> list[RelocationPlan]:
    """Derive deterministic relocation plans from failed ``det_*`` placement checks."""
    del domain  # reserved for domain-specific handlers
    section_by_id = _section_index(document)
    plans: list[RelocationPlan] = []

    for check in failed_checks:
        if not isinstance(check, dict):
            continue
        check_id = str(check.get("id", ""))
        if check_id not in PLACEMENT_CHECK_IDS:
            continue
        section_id = str(check.get("section_id") or "").strip()
        if not section_id:
            continue
        section = section_by_id.get(section_id)
        if section is None:
            continue

        handler = _CHECK_HANDLERS.get(check_id)
        if handler is None:
            continue

        relocations = handler(section, check)
        if relocations:
            plans.append(
                RelocationPlan(
                    check_id=check_id,
                    section_id=section_id,
                    relocations=relocations,
                )
            )
            check["relocation_plan"] = plans[-1].to_dict()

    return plans


def _section_index(document: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(section.get("id", "")).strip(): section
        for section in document.get("sections") or []
        if isinstance(section, dict) and str(section.get("id", "")).strip()
    }


def _parse_repr_string(raw: str) -> str:
    """Parse a Python repr string from block_placement_checks evidence."""
    text = str(raw or "").strip()
    if not text:
        return ""
    try:
        value = ast.literal_eval(text)
        return str(value) if value is not None else ""
    except (ValueError, SyntaxError):
        if len(text) >= 2 and text[0] == text[-1] and text[0] in "'\"":
            return text[1:-1]
        return text


def _parse_evidence_location(check: dict[str, Any]) -> tuple[str | None, str | None]:
    evidence = str(check.get("evidence", ""))
    match = _EVIDENCE_LOCATION_RE.match(evidence)
    if not match:
        return None, None
    section_heading = _parse_repr_string(match.group(1))
    subsection_raw = match.group(2)
    subsection_heading = (
        _parse_repr_string(subsection_raw) if subsection_raw is not None else None
    )
    return section_heading or None, subsection_heading or None


def _content_targets(
    section: dict[str, Any],
    *,
    subsection_heading: str | None,
) -> Iterator[tuple[str, str | None, dict[str, Any]]]:
    """Yield (content_text, subsection_heading, container_dict) pairs."""
    if subsection_heading:
        for subsection in section.get("subsections") or []:
            if not isinstance(subsection, dict):
                continue
            heading = str(subsection.get("heading", "")).strip()
            if heading == subsection_heading:
                yield str(subsection.get("content", "")), heading, subsection
                return
        return

    section_content = str(section.get("content", ""))
    if section_content:
        yield section_content, None, section


def _all_formula_texts(section: dict[str, Any]) -> list[str]:
    formulas: list[str] = []
    for block, _ in _formula_block_locations(section):
        formula = str(block.get("formula", "")).strip()
        if formula:
            formulas.append(formula)
    return formulas


def _span_in_formula_blocks(span_text: str, section: dict[str, Any]) -> bool:
    span_norm = normalize_math(span_text)
    if not span_norm:
        return False
    for formula in _all_formula_texts(section):
        formula_norm = normalize_math(formula)
        if span_norm in formula_norm or formula_norm in span_norm:
            return True
    return False


def _dereference_replacement(span_text: str) -> str:
    if "derivative" in span_text.lower() or "f'" in span_text:
        return "the derivative"
    if "integral" in span_text.lower() or "∫" in span_text:
        return "the integral"
    return "the expression"


def _plan_equation_in_content(
    section: dict[str, Any],
    check: dict[str, Any],
) -> list[Relocation]:
    _, subsection_heading = _parse_evidence_location(check)
    section_id = str(check.get("section_id", "")).strip()
    relocations: list[Relocation] = []

    for content, sub_heading, _container in _content_targets(
        section,
        subsection_heading=subsection_heading,
    ):
        seen_spans: set[tuple[int, int]] = set()
        for span in find_equation_spans(content):
            key = (span.start, span.end)
            if key in seen_spans:
                continue
            seen_spans.add(key)
            in_formula_blocks = _span_in_formula_blocks(span.text, section)
            if span.confidence != "high" and not in_formula_blocks:
                continue
            if in_formula_blocks:
                relocations.append(
                    Relocation(
                        action="dereference",
                        confidence="high",
                        section_id=section_id,
                        subsection_heading=sub_heading,
                        span_start=span.start,
                        span_end=span.end,
                        span_text=span.text,
                        replacement=_dereference_replacement(span.text),
                    )
                )
            elif is_narrative_equation_clause(span.text):
                core = extract_equation_core(span.text)
                if core and core in content[span.start : span.end]:
                    core_start = content.index(core, span.start, span.end)
                    core_end = core_start + len(core)
                    relocations.append(
                        Relocation(
                            action="extract",
                            confidence="high",
                            section_id=section_id,
                            subsection_heading=sub_heading,
                            span_start=core_start,
                            span_end=core_end,
                            span_text=core,
                        )
                    )
                else:
                    relocations.append(
                        Relocation(
                            action="dereference",
                            confidence="high",
                            section_id=section_id,
                            subsection_heading=sub_heading,
                            span_start=span.start,
                            span_end=span.end,
                            span_text=span.text,
                            replacement=_dereference_replacement(span.text),
                        )
                    )
            else:
                relocations.append(
                    Relocation(
                        action="extract",
                        confidence="high",
                        section_id=section_id,
                        subsection_heading=sub_heading,
                        span_start=span.start,
                        span_end=span.end,
                        span_text=span.text,
                    )
                )

        for match in re.finditer(r"f'\s*\([^)]*\)", content):
            key = (match.start(), match.end())
            if key in seen_spans:
                continue
            span_text = match.group()
            if not _span_in_formula_blocks(span_text, section):
                continue
            seen_spans.add(key)
            relocations.append(
                Relocation(
                    action="dereference",
                    confidence="high",
                    section_id=section_id,
                    subsection_heading=sub_heading,
                    span_start=match.start(),
                    span_end=match.end(),
                    span_text=span_text,
                    replacement=_dereference_replacement(span_text),
                )
            )

    return relocations


def _plan_math_in_code_block(
    section: dict[str, Any],
    check: dict[str, Any],
) -> list[Relocation]:
    _, subsection_heading = _parse_evidence_location(check)
    section_id = str(check.get("section_id", "")).strip()
    relocations: list[Relocation] = []

    for block, sub_heading, kind, index in _indexed_code_blocks(section):
        if subsection_heading and sub_heading != subsection_heading:
            continue
        lang = str(block.get("language", "")).strip()
        code = str(block.get("code", "")).strip()
        if not code or not _is_math_like_language(lang):
            continue
        relocations.append(
            Relocation(
                action="move_block",
                confidence="high",
                section_id=section_id,
                subsection_heading=sub_heading,
                block_kind=kind,
                block_index=index,
                target_kind="formula_blocks",
            )
        )

    return relocations


def _plan_code_in_formula_block(
    section: dict[str, Any],
    check: dict[str, Any],
) -> list[Relocation]:
    _, subsection_heading = _parse_evidence_location(check)
    section_id = str(check.get("section_id", "")).strip()
    relocations: list[Relocation] = []

    for block, sub_heading, kind, index in _indexed_formula_blocks(section):
        if subsection_heading and sub_heading != subsection_heading:
            continue
        formula = str(block.get("formula", "")).strip()
        if not formula or not looks_like_programming_code_in_formula(formula):
            continue
        relocations.append(
            Relocation(
                action="move_block",
                confidence="high",
                section_id=section_id,
                subsection_heading=sub_heading,
                block_kind=kind,
                block_index=index,
                target_kind="code_blocks",
            )
        )

    return relocations


def _plan_empty_block_explanation(
    section: dict[str, Any],
    check: dict[str, Any],
) -> list[Relocation]:
    evidence = str(check.get("evidence", "")).lower()
    _, subsection_heading = _parse_evidence_location(check)
    section_id = str(check.get("section_id", "")).strip()
    relocations: list[Relocation] = []

    if "formula_blocks" in evidence:
        iterator = _indexed_formula_blocks(section)
    else:
        iterator = _indexed_code_blocks(section)

    for block, sub_heading, kind, index in iterator:
        if subsection_heading and sub_heading != subsection_heading:
            continue
        explanation = str(block.get("explanation", "")).strip()
        body_key = "formula" if kind == "formula_blocks" else "code"
        body = str(block.get(body_key, "")).strip()
        if body and not explanation:
            relocations.append(
                Relocation(
                    action="fill_explanation",
                    confidence="high",
                    section_id=section_id,
                    subsection_heading=sub_heading,
                    block_kind=kind,
                    block_index=index,
                    explanation=_EMPTY_EXPLANATION_TEMPLATE,
                )
            )

    return relocations


def _plan_conceptual_has_blocks(
    section: dict[str, Any],
    check: dict[str, Any],
) -> list[Relocation]:
    del section
    section_id = str(check.get("section_id", "")).strip()
    return [
        Relocation(
            action="move_block",
            confidence="low",
            section_id=section_id,
        )
    ]


def _formula_block_locations(
    section: dict[str, Any],
) -> Iterator[tuple[dict[str, Any], str | None]]:
    for block in section.get("formula_blocks") or []:
        if isinstance(block, dict):
            yield block, None

    for subsection in section.get("subsections") or []:
        if not isinstance(subsection, dict):
            continue
        sub_heading = str(subsection.get("heading", "")).strip() or None
        for block in subsection.get("formula_blocks") or []:
            if isinstance(block, dict):
                yield block, sub_heading


def _code_block_locations(
    section: dict[str, Any],
) -> Iterator[tuple[dict[str, Any], str | None]]:
    for block in section.get("code_blocks") or []:
        if isinstance(block, dict):
            yield block, None

    for subsection in section.get("subsections") or []:
        if not isinstance(subsection, dict):
            continue
        sub_heading = str(subsection.get("heading", "")).strip() or None
        for block in subsection.get("code_blocks") or []:
            if isinstance(block, dict):
                yield block, sub_heading


def _indexed_code_blocks(
    section: dict[str, Any],
) -> Iterator[tuple[dict[str, Any], str | None, str, int]]:
    for index, block in enumerate(section.get("code_blocks") or []):
        if isinstance(block, dict):
            yield block, None, "code_blocks", index
    for subsection in section.get("subsections") or []:
        if not isinstance(subsection, dict):
            continue
        sub_heading = str(subsection.get("heading", "")).strip() or None
        for index, block in enumerate(subsection.get("code_blocks") or []):
            if isinstance(block, dict):
                yield block, sub_heading, "code_blocks", index


def _indexed_formula_blocks(
    section: dict[str, Any],
) -> Iterator[tuple[dict[str, Any], str | None, str, int]]:
    for index, block in enumerate(section.get("formula_blocks") or []):
        if isinstance(block, dict):
            yield block, None, "formula_blocks", index
    for subsection in section.get("subsections") or []:
        if not isinstance(subsection, dict):
            continue
        sub_heading = str(subsection.get("heading", "")).strip() or None
        for index, block in enumerate(subsection.get("formula_blocks") or []):
            if isinstance(block, dict):
                yield block, sub_heading, "formula_blocks", index


_CHECK_HANDLERS = {
    "det_equation_in_content": _plan_equation_in_content,
    "det_math_in_code_block": _plan_math_in_code_block,
    "det_code_in_formula_block": _plan_code_in_formula_block,
    "det_empty_block_explanation": _plan_empty_block_explanation,
    "det_conceptual_has_blocks": _plan_conceptual_has_blocks,
}
