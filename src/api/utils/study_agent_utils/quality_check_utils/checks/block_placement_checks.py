"""Deterministic document_coherence checks for code/formula block placement."""

from __future__ import annotations

import re
from collections.abc import Iterator
from typing import Any

from src.api.utils.study_agent_utils.generation.study_generation_json import (
    _is_math_like_language,
)

_PROGRAMMING_LANGUAGES = frozenset(
    {
        "python",
        "java",
        "javascript",
        "typescript",
        "c",
        "c++",
        "cpp",
        "csharp",
        "c#",
        "go",
        "rust",
        "ruby",
        "php",
        "kotlin",
        "swift",
        "scala",
        "bash",
        "shell",
        "sql",
    }
)

_DERIVATION_PATTERN = re.compile(
    r"\b(derive|derivation|prove|proof|calculate|step-by-step)\b",
    re.IGNORECASE,
)

_EQUATION_IN_CONTENT_PATTERNS = (
    re.compile(r"\\lim\b"),
    re.compile(r"\\frac\b"),
    re.compile(r"\\int\b"),
    re.compile(r"\$\$"),
    re.compile(r"f'\s*\("),
    re.compile(r"lim_\{"),
    re.compile(r"→|←|⇒"),
    re.compile(r"\\to\b"),
)

_PSEUDOCODE_PATTERNS = (
    re.compile(r"\)\s+then\b", re.IGNORECASE),
    re.compile(r"\bendif\b", re.IGNORECASE),
    re.compile(r"\bif\b.+\bthen\b", re.IGNORECASE),
)

_CODE_IN_FORMULA_PATTERNS = (
    re.compile(r"\bdef\s+\w+\s*\("),
    re.compile(r"\bclass\s+\w+"),
    re.compile(r"\bimport\s+\w+"),
    re.compile(r"\bfunction\s+\w+"),
)


def block_placement_checks(
    document: dict[str, Any],
    *,
    domain: str,
    checklist: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Return failed document_coherence checks for mis-placed blocks."""
    checks: list[dict[str, Any]] = []
    domain_key = str(domain or "").strip()

    for section in document.get("sections") or []:
        if not isinstance(section, dict):
            continue
        section_id = _section_id(section)
        section_heading = str(section.get("heading", "")).strip()

        for location, subsection_heading in _content_locations(section):
            if domain_key in ("STEM", "Mixed") and _looks_like_equation_in_content(
                location
            ):
                checks.append(
                    _failed_check(
                        check_id="det_equation_in_content",
                        section_id=section_id,
                        question="Are equations stored in formula_blocks rather than prose content?",
                        evidence=_location_evidence(
                            section_heading,
                            subsection_heading,
                            "Prose contains display-math patterns",
                        ),
                        corrective_hint=(
                            "Move equations and derivation steps from content into "
                            "formula_blocks with non-empty explanation fields."
                        ),
                    )
                )

        if domain_key == "Conceptual":
            if _has_executable_blocks(section):
                checks.append(
                    _failed_check(
                        check_id="det_conceptual_has_blocks",
                        section_id=section_id,
                        question="Does a Conceptual section avoid code_blocks and formula_blocks?",
                        evidence=_location_evidence(
                            section_heading,
                            None,
                            "Section contains code_blocks or formula_blocks",
                        ),
                        corrective_hint=(
                            "Remove code_blocks and formula_blocks from Conceptual "
                            "sections; express examples in prose."
                        ),
                    )
                )

        for block, subsection_heading in _code_block_locations(section):
            lang = str(block.get("language", "")).strip()
            code = str(block.get("code", "")).strip()
            if not code:
                continue

            if _is_math_like_language(lang):
                checks.append(
                    _failed_check(
                        check_id="det_math_in_code_block",
                        section_id=section_id,
                        question="Is math notation stored in formula_blocks instead of code_blocks?",
                        evidence=_location_evidence(
                            section_heading,
                            subsection_heading,
                            f"code_blocks language={lang!r}",
                        ),
                        corrective_hint=(
                            "Move math notation from code_blocks into formula_blocks."
                        ),
                    )
                )

            lang_key = lang.lower()
            if lang_key in _PROGRAMMING_LANGUAGES and _looks_like_pseudocode(code):
                checks.append(
                    _failed_check(
                        check_id="det_pseudocode_in_code_block",
                        section_id=section_id,
                        question="Does each code_block contain real programming code?",
                        evidence=_location_evidence(
                            section_heading,
                            subsection_heading,
                            "code_blocks body matches pseudocode heuristics",
                        ),
                        corrective_hint=(
                            "Replace pseudocode with valid executable code or move "
                            "algorithmic notation into formula_blocks."
                        ),
                    )
                )

            explanation = str(block.get("explanation", "")).strip()
            if not explanation:
                checks.append(
                    _failed_check(
                        check_id="det_empty_block_explanation",
                        section_id=section_id,
                        question="Does every code_block have a non-empty explanation?",
                        evidence=_location_evidence(
                            section_heading,
                            subsection_heading,
                            "code_blocks has content but empty explanation",
                        ),
                        corrective_hint="Add a 2-3 sentence explanation to the code_block.",
                    )
                )

        for block, subsection_heading in _formula_block_locations(section):
            formula = str(block.get("formula", "")).strip()
            if not formula:
                continue

            if _looks_like_programming_code(formula):
                checks.append(
                    _failed_check(
                        check_id="det_code_in_formula_block",
                        section_id=section_id,
                        question="Do formula_blocks contain equations rather than programming code?",
                        evidence=_location_evidence(
                            section_heading,
                            subsection_heading,
                            "formula_blocks body contains programming keywords",
                        ),
                        corrective_hint=(
                            "Move programming code into code_blocks; keep only "
                            "equations or derivations in formula_blocks."
                        ),
                    )
                )

            explanation = str(block.get("explanation", "")).strip()
            if not explanation:
                checks.append(
                    _failed_check(
                        check_id="det_empty_block_explanation",
                        section_id=section_id,
                        question="Does every formula_block have a non-empty explanation?",
                        evidence=_location_evidence(
                            section_heading,
                            subsection_heading,
                            "formula_blocks has content but empty explanation",
                        ),
                        corrective_hint=(
                            "Add a 2-3 sentence explanation to the formula_block."
                        ),
                    )
                )

    if domain_key == "STEM":
        checklist_items = checklist or []
        checks.extend(
            _stem_derivation_missing_formula_checks(document, checklist_items)
        )
        checks.extend(
            _stem_code_substitutes_derivation_checks(document, checklist_items)
        )

    return checks


def _stem_derivation_missing_formula_checks(
    document: dict[str, Any],
    checklist: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    section_by_id = {
        _section_id(section): section
        for section in document.get("sections") or []
        if isinstance(section, dict) and _section_id(section)
    }

    for item in checklist:
        if not isinstance(item, dict):
            continue
        requirement = str(item.get("requirement", ""))
        depth_gate = str(item.get("depth_gate", ""))
        combined = f"{requirement} {depth_gate}".strip()
        if not combined or not _DERIVATION_PATTERN.search(combined):
            continue

        target_id = str(item.get("section_id") or item.get("id") or "").strip()
        if not target_id:
            continue

        section = section_by_id.get(target_id)
        if section is None:
            continue

        if _section_has_formula_blocks(section):
            continue

        section_heading = str(section.get("heading", "")).strip()
        checks.append(
            _failed_check(
                check_id="det_stem_derivation_missing_formula",
                section_id=target_id,
                question=(
                    "Does a STEM derivation checklist item have formula_blocks "
                    "showing the steps?"
                ),
                evidence=(
                    f"Section {target_id!r} ({section_heading or 'untitled'}) "
                    f"requires derivation depth ({depth_gate or requirement!r}) "
                    "but has no formula_blocks."
                ),
                corrective_hint=(
                    "Add formula_blocks with step-by-step derivation for this section."
                ),
            )
        )

    return checks


def _stem_code_substitutes_derivation_checks(
    document: dict[str, Any],
    checklist: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Fail when a derivation checklist section contains programming code_blocks."""
    checks: list[dict[str, Any]] = []
    section_by_id = {
        _section_id(section): section
        for section in document.get("sections") or []
        if isinstance(section, dict) and _section_id(section)
    }

    for item in checklist:
        if not isinstance(item, dict):
            continue
        requirement = str(item.get("requirement", ""))
        depth_gate = str(item.get("depth_gate", ""))
        combined = f"{requirement} {depth_gate}".strip()
        if not combined or not _DERIVATION_PATTERN.search(combined):
            continue

        target_id = str(item.get("section_id") or item.get("id") or "").strip()
        if not target_id:
            continue

        section = section_by_id.get(target_id)
        if section is None:
            continue

        if not _section_has_code_blocks(section):
            continue

        section_heading = str(section.get("heading", "")).strip()
        checks.append(
            _failed_check(
                check_id="det_stem_code_substitutes_derivation",
                section_id=target_id,
                question=(
                    "Does a STEM derivation section avoid code_blocks when the "
                    "checklist demands algebraic steps?"
                ),
                evidence=(
                    f"Section {target_id!r} ({section_heading or 'untitled'}) "
                    f"has code_blocks but checklist item requires derivation depth "
                    f"({depth_gate or requirement!r})."
                ),
                corrective_hint=(
                    "Remove code_blocks from this section and show the derivation "
                    "as sequential steps in formula_blocks."
                ),
            )
        )

    return checks


def _section_id(section: dict[str, Any]) -> str | None:
    raw = section.get("id")
    if raw is None:
        return None
    text = str(raw).strip()
    return text or None


def _content_locations(section: dict[str, Any]) -> Iterator[tuple[str, str | None]]:
    section_content = str(section.get("content", "")).strip()
    if section_content:
        yield section_content, None

    for subsection in section.get("subsections") or []:
        if not isinstance(subsection, dict):
            continue
        sub_content = str(subsection.get("content", "")).strip()
        if sub_content:
            yield sub_content, str(subsection.get("heading", "")).strip() or None


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


def _has_executable_blocks(section: dict[str, Any]) -> bool:
    if section.get("code_blocks") or section.get("formula_blocks"):
        return True
    for subsection in section.get("subsections") or []:
        if not isinstance(subsection, dict):
            continue
        if subsection.get("code_blocks") or subsection.get("formula_blocks"):
            return True
    return False


def _section_has_formula_blocks(section: dict[str, Any]) -> bool:
    for block, _ in _formula_block_locations(section):
        if str(block.get("formula", "")).strip():
            return True
    return False


def _section_has_code_blocks(section: dict[str, Any]) -> bool:
    for block, _ in _code_block_locations(section):
        if str(block.get("code", "")).strip():
            return True
    return False


def _looks_like_equation_in_content(text: str) -> bool:
    return any(pattern.search(text) for pattern in _EQUATION_IN_CONTENT_PATTERNS)


def _looks_like_pseudocode(code: str) -> bool:
    if any(pattern.search(code) for pattern in _PSEUDOCODE_PATTERNS):
        return True
    if ("→" in code or "←" in code) and not re.search(
        r"\b(def|class|import|function)\b", code
    ):
        return True
    return False


def _looks_like_programming_code(formula: str) -> bool:
    return any(pattern.search(formula) for pattern in _CODE_IN_FORMULA_PATTERNS)


def _location_evidence(
    section_heading: str,
    subsection_heading: str | None,
    detail: str,
) -> str:
    if subsection_heading:
        return (
            f"Section {section_heading!r}, subsection {subsection_heading!r}: {detail}"
        )
    return f"Section {section_heading!r}: {detail}"


def _failed_check(
    *,
    check_id: str,
    section_id: str | None,
    question: str,
    evidence: str,
    corrective_hint: str,
) -> dict[str, Any]:
    check: dict[str, Any] = {
        "id": check_id,
        "category": "document_coherence",
        "question": question,
        "passed": False,
        "severity": "critical",
        "evidence": evidence,
        "corrective_hint": corrective_hint,
    }
    if section_id:
        check["section_id"] = section_id
    return check
