# src/api/utils/study_agent_utils/qc/deterministic.py
"""Deterministic QC extraction and checks — no LLM.

Runs in ``quality_check_node`` phase 1 before Groq verification:

  - ``extract_structure_from_document`` — sections + code artifacts (``code_1``, …)
  - ``structure_check`` / ``structure_coverage_missing_ids`` — ``det_structure_coverage``
  - ``block_placement_checks`` (separate module) — ``det_equation_in_content``, etc.
  - ``attach_code_artifact_ids_from_document`` — map code QC checks to section ids

Deterministic failures with ``section_id`` route to **section_patch** via
``classify_retry_routing`` (not full regen unless escalation thresholds fire).
"""

from __future__ import annotations

from typing import Any

from src.api.schemas.qc_schemas.qc_document_structure_schema import (
    CodeArtifact,
    DocumentStructure,
)
from src.api.utils.study_agent_utils.generation.study_generation_json import (
    parse_generation_document,
    validate_section_id_coverage,
)


def extract_structure(content: str) -> DocumentStructure:
    """Parse sections and code blocks from a canonical JSON study document."""
    doc = parse_generation_document(content)
    if doc is None:
        return DocumentStructure(sections=[], code_artifacts=[], has_preamble=False)
    return extract_structure_from_document(doc)


def extract_structure_from_document(document: dict[str, Any]) -> DocumentStructure:
    """Extract structure directly from a parsed document dict."""
    sections: list[dict[str, Any]] = []
    artifacts: list[CodeArtifact] = []
    artifact_index = 0

    for section in document.get("sections") or []:
        if not isinstance(section, dict):
            continue
        section_id = section.get("id")
        section_id_str = str(section_id).strip() if section_id is not None else None
        heading = str(section.get("heading", "")).strip()
        sections.append(
            {
                "id": section_id_str,
                "heading": heading,
                "content": str(section.get("content", "")),
                "subsections": section.get("subsections") or [],
            }
        )

        for block in section.get("code_blocks") or []:
            if not isinstance(block, dict):
                continue
            artifact_index += 1
            artifacts.append(
                _code_artifact_from_block(
                    block,
                    artifact_index=artifact_index,
                    section_id=section_id_str,
                    section_heading=heading or None,
                )
            )

        for subsection in section.get("subsections") or []:
            if not isinstance(subsection, dict):
                continue
            sub_heading = str(subsection.get("heading", "")).strip() or None
            for block in subsection.get("code_blocks") or []:
                if not isinstance(block, dict):
                    continue
                artifact_index += 1
                artifacts.append(
                    _code_artifact_from_block(
                        block,
                        artifact_index=artifact_index,
                        section_id=section_id_str,
                        section_heading=heading or None,
                        subsection_heading=sub_heading,
                    )
                )

    return DocumentStructure(
        sections=sections,
        code_artifacts=artifacts,
        has_preamble=False,
    )


def _code_artifact_from_block(
    block: dict[str, Any],
    *,
    artifact_index: int,
    section_id: str | None,
    section_heading: str | None,
    subsection_heading: str | None = None,
) -> CodeArtifact:
    lang = str(block.get("language", "")).strip().lower()
    body = str(block.get("code", ""))
    line_count = body.count("\n") + 1 if body else 0
    fenced = f"```{lang}\n{body.rstrip()}\n```"
    return CodeArtifact(
        id=f"code_{artifact_index}",
        language=lang,
        body=body,
        fenced_code=fenced,
        line_count=line_count,
        section_id=section_id,
        section_heading=section_heading,
        subsection_heading=subsection_heading,
    )


def structure_coverage_missing_ids(
    doc: dict[str, Any],
    checklist: list[dict[str, Any]] | None = None,
    *,
    topic_split: list[dict[str, Any]] | None = None,
) -> set[str]:
    """Return required section ids absent from *doc* (single coverage computation)."""
    coverage = validate_section_id_coverage(
        doc, checklist or [], topic_split=topic_split
    )
    return set(coverage.missing_ids)


def structure_check_from_missing_ids(
    missing_ids: set[str] | frozenset[str],
) -> dict[str, Any] | None:
    """Build det_structure_coverage failure check from precomputed missing ids."""
    if not missing_ids:
        return None
    missing = ", ".join(sorted(missing_ids))
    return {
        "id": "det_structure_coverage",
        "category": "structure",
        "question": "Does every required topic_split / checklist section exist in the document?",
        "passed": False,
        "severity": "critical",
        "evidence": f"Missing section ids: {missing}",
        "corrective_hint": "Add one section per topic_split entry (or required checklist item) with matching id.",
    }


def structure_check(
    structure: DocumentStructure,
    *,
    checklist: list[dict[str, Any]] | None = None,
    doc: dict[str, Any] | None = None,
    topic_split: list[dict[str, Any]] | None = None,
    structure_missing_ids: set[str] | frozenset[str] | None = None,
) -> dict[str, Any] | None:
    """Return a failed check when required section ids are missing."""
    del structure
    if doc is None:
        return None
    missing_ids = (
        set(structure_missing_ids)
        if structure_missing_ids is not None
        else structure_coverage_missing_ids(doc, checklist, topic_split=topic_split)
    )
    return structure_check_from_missing_ids(missing_ids)


def _infer_section_type(heading: str) -> str:
    h = heading.lower()
    if "mistake" in h:
        return "mistakes"
    if "pitfall" in h:
        return "pitfalls"
    if "example" in h:
        return "example"
    if "walkthrough" in h:
        return "walkthrough"
    return "explanation"


def attach_code_artifact_ids_from_document(
    checks: list[dict[str, Any]],
    document: dict[str, Any],
) -> list[dict[str, Any]]:
    """Fill section_id on code checks from document code block order."""
    artifact_map = {
        art.id: art.section_id
        for art in extract_structure_from_document(document).code_artifacts
    }
    for check in checks:
        if str(check.get("category")) not in ("code_quality", "stack_fidelity"):
            continue
        if check.get("section_id"):
            continue
        artifact_id = str(check.get("code_artifact_id", "")).strip()
        if not artifact_id:
            check_id = str(check.get("id", ""))
            if check_id.startswith("det_code_"):
                artifact_id = check_id.replace("det_", "", 1)
        if artifact_id and artifact_id in artifact_map:
            section_id = artifact_map[artifact_id]
            if section_id:
                check["section_id"] = section_id
    return checks


def build_code_review_payloads(structure: DocumentStructure) -> list[dict[str, Any]]:
    """One entry per code block — used for extraction logging and diagnostics."""
    payloads: list[dict[str, Any]] = []
    section_by_id = {
        str(section.get("id", "")): section
        for section in structure.sections
        if section.get("id")
    }

    for art in structure.code_artifacts:
        section = section_by_id.get(art.section_id or "")
        section_heading = art.section_heading or (
            str(section.get("heading", "")) if section else ""
        )
        section_type = _infer_section_type(section_heading)
        section_json = section or {}

        payload: dict[str, Any] = {
            "id": art.id,
            "language": art.language or "unknown",
            "fenced_code": art.fenced_code,
            "section_id": art.section_id,
            "section_heading": section_heading,
            "section_type": section_type,
            "section_json": section_json,
        }
        if art.subsection_heading:
            payload["subsection_heading"] = art.subsection_heading
        payloads.append(payload)
    return payloads
