# src/api/utils/study_agent_utils/study_generation_json.py
"""Parse, canonicalize, and render study material JSON from the generator."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from src.api.schemas.study_material_schemas import (
    GenerationDocument,
)
from src.api.schemas.study_material_schemas.generation_outcome_schema import (
    ActionRequiredOut,
    ApiGenerationOutcome,
    GenerationOutcomeDetail,
    GraphGenerationOutcome,
)
from src.api.utils.study_agent_utils.generation.must_cover_checklist_format import (
    checklist_section_id,
)

_REFERENCE_REQUIRED_STATUS = "reference_required"
_RAW_PREVIEW_MAX_LEN = 500
_GENERATOR_ERROR_REASON = "Generator response is not valid JSON"
_MALFORMED_REASON = "Document failed domain validation"


@dataclass(frozen=True)
class ClassifiedGenerationOutput:
    canonical_json: str
    outcome: GraphGenerationOutcome
    document: dict[str, Any] | None
    detail: dict[str, Any]


@dataclass
class SectionCoverageResult:
    found_ids: set[str]
    missing_ids: set[str]


def is_reference_required_response(doc: dict[str, Any]) -> bool:
    return (
        GenerationDocument.from_dict(doc).generation_status
        == _REFERENCE_REQUIRED_STATUS
    )


def is_vague_improve_response(doc: dict[str, Any]) -> bool:
    return (
        str(GenerationDocument.from_dict(doc).improve_status or "").strip() == "vague"
    )


def is_vague_regenerate_response(doc: dict[str, Any]) -> bool:
    return (
        str(GenerationDocument.from_dict(doc).regenerate_status or "").strip()
        == "vague"
    )


def is_status_only_response(doc: dict[str, Any]) -> bool:
    return GenerationDocument.from_dict(doc).is_status_only()


def parse_generation_document(raw: str) -> dict[str, Any] | None:
    """Parse generator output into a document or status dict."""
    from src.api.utils.study_agent_utils.quality_check_utils.parsing.json_parse import (
        parse_llm_json_object,
    )

    parsed = parse_llm_json_object(raw, "generation")
    if parsed is None:
        return None
    sections = parsed.get("sections")
    if sections is not None and not isinstance(sections, list):
        return None
    if is_status_only_response(parsed):
        return parsed
    if not isinstance(parsed.get("sections"), list):
        return None
    return parsed


def _parse_for_canonicalization(
    raw: str,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """Parse generator output once for canonicalization and domain validation."""
    from src.api.utils.study_agent_utils.quality_check_utils.parsing.json_parse import (
        parse_llm_json_object,
    )

    document = parse_generation_document(raw)
    if document is not None:
        return document, document
    parsed = parse_llm_json_object(raw, "generation")
    if parsed is None:
        raise ValueError(_GENERATOR_ERROR_REASON)
    return parsed, None


def _status_outcome_detail(document: dict[str, Any]) -> dict[str, Any]:
    detail = GenerationOutcomeDetail(
        message=_optional_str(document.get("message")),
        reason=_optional_str(document.get("reason")),
        topic_received=_optional_str(document.get("topic_received")),
    )
    return detail.model_dump(exclude_none=True)


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _raw_preview(canonical_json: str) -> str:
    if len(canonical_json) <= _RAW_PREVIEW_MAX_LEN:
        return canonical_json
    return f"{canonical_json[:_RAW_PREVIEW_MAX_LEN]}..."


def classify_generation_output(raw: str) -> ClassifiedGenerationOutput:
    """Classify generator output into a graph routing outcome and parsed document."""
    try:
        parsed, document = _parse_for_canonicalization(raw)
        canonical_json = json.dumps(parsed, separators=(",", ":"), ensure_ascii=False)
    except ValueError:
        return ClassifiedGenerationOutput(
            canonical_json=raw.strip(),
            outcome="generator_error",
            document=None,
            detail={"reason": _GENERATOR_ERROR_REASON},
        )

    if document is None:
        return ClassifiedGenerationOutput(
            canonical_json=canonical_json,
            outcome="malformed_document",
            document=None,
            detail={
                "reason": _MALFORMED_REASON,
                "raw_preview": _raw_preview(canonical_json),
            },
        )

    if is_status_only_response(document):
        if is_reference_required_response(document):
            outcome: GraphGenerationOutcome = "reference_required"
        else:
            outcome = "vague_feedback"
        return ClassifiedGenerationOutput(
            canonical_json=canonical_json,
            outcome=outcome,
            document=document,
            detail=_status_outcome_detail(document),
        )

    return ClassifiedGenerationOutput(
        canonical_json=canonical_json,
        outcome="study_document",
        document=document,
        detail={},
    )


def build_action_required(
    outcome: GraphGenerationOutcome | ApiGenerationOutcome,
    detail: dict[str, Any] | GenerationOutcomeDetail | None,
) -> ActionRequiredOut | None:
    """Build mentor-facing action guidance for terminal status outcomes."""
    detail_data = _coerce_outcome_detail(detail)
    if outcome == "reference_required":
        return ActionRequiredOut(
            type="upload_reference",
            message=detail_data.get("message")
            or "Reference material is required before generating study content.",
            topic_received=detail_data.get("topic_received"),
            reason=detail_data.get("reason"),
        )
    if outcome == "vague_feedback":
        return ActionRequiredOut(
            type="clarify_feedback",
            message=detail_data.get("message")
            or "Please provide more specific feedback before continuing.",
            topic_received=detail_data.get("topic_received"),
            reason=detail_data.get("reason"),
        )
    return None


def _coerce_outcome_detail(
    detail: dict[str, Any] | GenerationOutcomeDetail | None,
) -> dict[str, Any]:
    if detail is None:
        return {}
    if isinstance(detail, GenerationOutcomeDetail):
        return detail.model_dump(exclude_none=True)
    return {key: value for key, value in detail.items() if value is not None}


def render_outcome_content(
    canonical_json: str,
    outcome: GraphGenerationOutcome,
    detail: dict[str, Any] | GenerationOutcomeDetail | None = None,
) -> str:
    """Render mentor-facing persisted content for a classified generation outcome."""
    detail_data = _coerce_outcome_detail(detail)
    if outcome == "study_document":
        document = json.loads(canonical_json)
        return render_sections_to_markdown(document)
    if outcome in {"reference_required", "vague_feedback"}:
        document = json.loads(canonical_json)
        return render_sections_to_markdown(document)
    if outcome == "malformed_document":
        lines = [
            "GENERATION STATUS: Malformed document",
            "The generator returned JSON that could not be validated as a study document.",
        ]
        preview = detail_data.get("raw_preview")
        if preview:
            lines.append(f"Preview: {preview}")
        reason = detail_data.get("reason")
        if reason:
            lines.append(f"Reason: {reason}")
        return "\n".join(lines)
    if outcome == "generator_error":
        message = (
            detail_data.get("message")
            or detail_data.get("reason")
            or _GENERATOR_ERROR_REASON
        )
        return f"GENERATION ERROR: {message}"
    return canonical_json


def canonicalize_generation_json(raw: str) -> str:
    """Strip fences/commentary and return one compact JSON object string."""
    classified = classify_generation_output(raw)
    if classified.outcome == "generator_error":
        raise ValueError(classified.detail.get("reason", _GENERATOR_ERROR_REASON))
    return classified.canonical_json


def canonicalize_generation_content(raw: str) -> tuple[str, dict[str, Any] | None]:
    """Return compact JSON and a domain-valid document when one is present."""
    classified = classify_generation_output(raw)
    if classified.outcome == "generator_error":
        raise ValueError(classified.detail.get("reason", _GENERATOR_ERROR_REASON))
    return classified.canonical_json, classified.document


def try_canonicalize_generation_json(raw: str) -> str | None:
    try:
        return canonicalize_generation_json(raw)
    except ValueError:
        return None


def resolve_checklist_section_id(
    checklist: list[dict[str, Any]],
    checklist_item_id: str,
) -> str:
    """Map a must_cover checklist id to the document section id it targets."""
    raw = str(checklist_item_id).strip()
    if not raw:
        return raw
    for item in checklist:
        if str(item.get("id", "")).strip() == raw:
            return checklist_section_id(item)
    return raw


def expected_document_section_ids(
    checklist: list[dict[str, Any]],
    topic_split: list[dict[str, Any]] | None = None,
) -> set[str]:
    """Section ids the document must contain (topic_split blueprint or legacy checklist ids)."""
    if topic_split:
        return {
            str(entry.get("id", "")).strip()
            for entry in topic_split
            if isinstance(entry, dict) and str(entry.get("id", "")).strip()
        }
    return {
        str(item.get("id", "")).strip()
        for item in checklist
        if str(item.get("priority", "")).lower() == "required" and item.get("id")
    }


def validate_section_id_coverage(
    doc: dict[str, Any],
    checklist: list[dict[str, Any]],
    *,
    topic_split: list[dict[str, Any]] | None = None,
) -> SectionCoverageResult:
    """Compare section ``id`` fields against the topic blueprint or checklist items."""
    required_ids = expected_document_section_ids(checklist, topic_split)
    found_ids: set[str] = set()
    for section in doc.get("sections") or []:
        if not isinstance(section, dict):
            continue
        section_id = section.get("id")
        if section_id is not None and str(section_id).strip():
            found_ids.add(str(section_id).strip())
    missing_ids = required_ids - found_ids
    return SectionCoverageResult(
        found_ids=found_ids,
        missing_ids=missing_ids,
    )


def _heading_line(heading: str, level: int = 2) -> str:
    text = heading.strip()
    if not text:
        return ""
    if text.startswith("#"):
        return text
    prefix = "#" * level
    return f"{prefix} {text}"


def _is_math_like_language(language: str) -> bool:
    return language.strip().lower() in {
        "math",
        "mathematics",
        "latex",
        "tex",
        "chemical equation",
        "chemistry",
    }


def _strip_math_delimiters(formula: str) -> str:
    """Strip leading/trailing LaTeX math delimiters ($, $$) from a formula string.

    The LLM often outputs formulas that already include ``$...$`` or
    ``$$...$$`` delimiters.  If we blindly wrap those in ``$$\\n...\\n$$``
    we end up with ``$$\\n$formula$\\n$$`` which KaTeX cannot parse and
    renders as raw red text.  This helper normalises the body so the
    caller always gets bare LaTeX.
    """
    body = formula.strip()
    # Display math: $$...$$
    if body.startswith("$$") and body.endswith("$$") and len(body) > 4:
        return body[2:-2].strip()
    # Inline math: $...$  (but avoid stripping a lone $ sign)
    if body.startswith("$") and body.endswith("$") and len(body) > 2:
        return body[1:-1].strip()
    return body


def _strip_markdown_fences(text: str) -> str:
    """Remove outer markdown code fences when the LLM already wrapped the payload."""
    body = text.strip()
    for _ in range(3):
        if not body.startswith("```"):
            return body
        lines = body.split("\n")
        close_idx = next(
            (
                index
                for index in range(len(lines) - 1, 0, -1)
                if lines[index].strip() == "```"
            ),
            None,
        )
        if close_idx is None:
            return body
        inner = "\n".join(lines[1:close_idx]).strip("\n")
        if inner == body:
            return body
        body = inner
    return body


def _render_formula_block(formula: str, *, notation: str = "") -> list[str]:
    body = _strip_math_delimiters(_strip_markdown_fences(formula).strip())
    if not body:
        return []
    notation_key = notation.strip().lower()
    if notation_key in {"", "latex", "tex", "math", "mathematics"}:
        return [f"$$\n{body}\n$$"]
    return [f"```\n{body}\n```"]


def _append_code_or_formula_blocks(parts: list[str], blocks: list[Any]) -> None:
    for block in blocks:
        if not isinstance(block, dict):
            continue
        lang = str(block.get("language", "")).strip()
        code = _strip_markdown_fences(str(block.get("code", "")).rstrip())
        if not code:
            continue
        if _is_math_like_language(lang):
            parts.extend(_render_formula_block(code))
        else:
            parts.append(f"```{lang}\n{code}\n```")
        explanation = str(block.get("explanation", "")).strip()
        if explanation:
            parts.append(explanation)


def _append_formula_blocks(parts: list[str], blocks: list[Any]) -> None:
    for block in blocks:
        if not isinstance(block, dict):
            continue
        formula = str(block.get("formula", "")).rstrip()
        if not formula:
            continue
        notation = str(block.get("notation", "")).strip()
        parts.extend(_render_formula_block(formula, notation=notation))
        explanation = str(block.get("explanation", "")).strip()
        if explanation:
            parts.append(explanation)


def render_sections_to_markdown(doc: dict[str, Any]) -> str:
    """Render JSON sections to trainee-facing markdown."""
    if is_reference_required_response(doc):
        topic = doc.get("topic_received", "")
        reason = doc.get("reason", "")
        message = doc.get("message", "")
        lines = [
            "GENERATION STATUS: Reference material required",
            str(message).strip(),
        ]
        if topic:
            lines.append(f"Topic received: {topic}")
        if reason:
            lines.append(f"Reason: {reason}")
        return "\n".join(line for line in lines if line).strip()

    if is_vague_improve_response(doc):
        return str(
            doc.get("message", "IMPROVE STATUS: Feedback too vague to apply.")
        ).strip()

    if is_vague_regenerate_response(doc):
        return str(
            doc.get(
                "message", "REGENERATE STATUS: Regeneration goal too vague to apply."
            )
        ).strip()

    parts: list[str] = []
    for section in doc.get("sections") or []:
        if not isinstance(section, dict):
            continue
        heading = _heading_line(str(section.get("heading", "")))
        if heading:
            parts.append(heading)
        content = str(section.get("content", "")).strip()
        if content:
            parts.append(content)
        _append_code_or_formula_blocks(parts, section.get("code_blocks") or [])
        _append_formula_blocks(parts, section.get("formula_blocks") or [])
        for subsection in section.get("subsections") or []:
            if not isinstance(subsection, dict):
                continue
            sub_heading = _heading_line(str(subsection.get("heading", "")), level=3)
            if sub_heading:
                parts.append(sub_heading)
            sub_content = str(subsection.get("content", "")).strip()
            if sub_content:
                parts.append(sub_content)
            _append_code_or_formula_blocks(parts, subsection.get("code_blocks") or [])
            _append_formula_blocks(parts, subsection.get("formula_blocks") or [])
    return "\n\n".join(parts).strip()


def content_for_persistence(raw_content: str) -> str:
    """Render JSON study documents to markdown; pass through legacy markdown."""
    text = raw_content.strip()
    if not text.startswith("{"):
        return text
    classified = classify_generation_output(text)
    if classified.outcome == "generator_error":
        return text
    return render_outcome_content(
        classified.canonical_json,
        classified.outcome,
        classified.detail,
    )


def normalize_checklist_id(check_id: str, checklist: list[dict[str, Any]]) -> str:
    """Map bare numeric ids (e.g. ``3``) to checklist ids (e.g. ``mc_3``)."""
    raw = str(check_id).strip()
    if not raw or not checklist:
        return raw

    valid_ids = {str(item.get("id", "")) for item in checklist}
    if raw in valid_ids:
        return raw

    prefixed = f"mc_{raw}"
    if prefixed in valid_ids:
        return prefixed

    for item in checklist:
        item_id = str(item.get("id", ""))
        if item_id.endswith(f"_{raw}") or item_id == raw:
            return item_id

    return raw


def normalize_checklist_ids(
    checks: list[dict[str, Any]],
    checklist: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Normalize checklist_id fields on must_cover checks after LLM parse."""
    if not checklist:
        return checks

    for check in checks:
        if str(check.get("category")) != "must_cover":
            continue
        raw = check.get("checklist_id") or check.get("id")
        if raw:
            normalized = normalize_checklist_id(str(raw), checklist)
            check["checklist_id"] = normalized
            check["id"] = normalized
    return checks


def normalize_must_cover_section_ids(
    checks: list[dict[str, Any]],
    checklist: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Fill missing/wrong section_id on must_cover from checklist mapping."""
    if not checklist:
        return checks

    for check in checks:
        if str(check.get("category")) != "must_cover":
            continue
        raw = check.get("checklist_id") or check.get("id")
        if not raw:
            continue
        checklist_id = normalize_checklist_id(str(raw), checklist)
        canonical = resolve_checklist_section_id(checklist, checklist_id)
        if not canonical:
            continue
        current = str(check.get("section_id", "") or "").strip()
        if current == canonical:
            continue
        check["section_id"] = canonical
    return checks


# Re-export generation document shapes for convenience.
