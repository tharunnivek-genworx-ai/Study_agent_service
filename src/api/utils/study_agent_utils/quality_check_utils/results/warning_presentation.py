"""Build mentor-facing QC warning copy from failed checks and concept plan."""

from __future__ import annotations

import re
from typing import Any, Literal

DetDisplayTier = Literal["formatting", "structure", "evidence"]
QcWarningKind = Literal["det_only", "llm_content", "mixed"]

FORMATTING_DET_IDS = frozenset(
    {
        "det_equation_in_content",
        "det_math_in_code_block",
        "det_code_in_formula_block",
        "det_conceptual_has_blocks",
        "det_empty_block_explanation",
    }
)

STRUCTURE_DET_IDS = frozenset({"det_structure_coverage"})

EVIDENCE_DET_IDS = frozenset(
    {
        "det_stem_derivation_missing_formula",
        "det_stem_code_substitutes_derivation",
        "det_pseudocode_in_code_block",
    }
)

QC_LLM_FAILED_TITLE = "Quality review recommended"
QC_LLM_FAILED_BODY = (
    "This study material did not pass our quality analysis. That does not mean "
    "the content is invalid or weak — it means it did not meet our company-set "
    "standards. Read the draft carefully and review the report below before "
    "discarding or proceeding with this draft."
)

DET_FORMATTING_TITLE = "Document formatting note"
DET_FORMATTING_BODY = (
    "The teaching content looks strong, but a few sections do not follow our "
    "internal document structure rules (for example, equations belong in formula "
    "blocks, not inline in prose). This does not mean the math is wrong. Skim "
    "the sections listed below — you can continue with this draft if the material "
    "reads well to you."
)

DET_STRUCTURE_TITLE = "Document structure incomplete"
DET_STRUCTURE_BODY = (
    "The draft is missing one or more planned sections. Review the outline before "
    "publishing — some topics from your plan may not appear in the material."
)

DET_EVIDENCE_TITLE = "Teaching depth not fully demonstrated"
DET_EVIDENCE_BODY = (
    "Some required teaching evidence (step-by-step derivations or runnable code) "
    "is missing or in the wrong format. The topic may still read well, but it may "
    "not meet the depth bar set in your plan."
)

MIXED_TITLE = "Quality review recommended"
MIXED_BODY = (
    "This draft has both formatting structure notes and content items that did not "
    "fully pass review. Read the draft carefully and use the sections below before "
    "deciding how to proceed."
)

FORMATTING_REASSURANCE = (
    "Automated retries could not resolve formatting-only rules; content scores "
    "suggest the material is otherwise ready."
)

SECTION_ID_PATTERN = re.compile(r"\bts_\d+\b")

DET_USER_MESSAGE_BUILDERS: dict[str, Any] = {
    "det_equation_in_content": lambda section, _subsection=None: (
        f"{section} — some equations appear inline in the paragraph text instead "
        "of in dedicated formula blocks."
    ),
    "det_math_in_code_block": lambda section, _subsection=None: (
        f"{section} — math notation was placed in a code block; it should be in a "
        "formula block."
    ),
    "det_code_in_formula_block": lambda section, _subsection=None: (
        f"{section} — programming code was placed in a formula block; it should be "
        "in a code block."
    ),
    "det_conceptual_has_blocks": lambda section, _subsection=None: (
        f"{section} — this conceptual section includes code or formula blocks; it "
        "should be prose-only."
    ),
    "det_empty_block_explanation": lambda section, _subsection=None: (
        f"{section} — a code or formula block is missing its explanation text."
    ),
    "det_structure_coverage": lambda _section, _subsection=None: (
        "One or more planned sections are missing from the draft."
    ),
    "det_stem_derivation_missing_formula": lambda section, _subsection=None: (
        f"{section} — a derivation was required but the step-by-step working is not "
        "shown in formula blocks."
    ),
    "det_stem_code_substitutes_derivation": lambda section, _subsection=None: (
        f"{section} — a mathematical derivation was required, but the section uses "
        "code instead of algebraic steps."
    ),
    "det_pseudocode_in_code_block": lambda section, _subsection=None: (
        f"{section} — a code example may not be runnable as written."
    ),
}


def build_section_label_map(concept_plan: dict[str, Any] | None) -> dict[str, str]:
    labels: dict[str, str] = {}
    if not concept_plan:
        return labels
    for section in concept_plan.get("topic_split") or []:
        if not isinstance(section, dict):
            continue
        section_id = str(section.get("id") or "").strip()
        heading = str(section.get("heading") or "").strip()
        if section_id and heading:
            labels[section_id] = heading
    return labels


def humanize_qc_text(
    text: str | None,
    section_labels: dict[str, str],
) -> str:
    if not text or not text.strip():
        return text or ""

    result = text

    def _revised_section(match: re.Match[str]) -> str:
        section_id = match.group(1)
        heading = section_labels.get(section_id)
        return f'"{heading}" section' if heading else "relevant section"

    result = re.sub(
        r"\brevised section (ts_\d+)\b",
        _revised_section,
        result,
        flags=re.IGNORECASE,
    )

    def _section(match: re.Match[str]) -> str:
        section_id = match.group(1)
        heading = section_labels.get(section_id)
        if heading:
            return f'the "{heading}" section'
        return "the relevant section"

    result = re.sub(r"\bsection (ts_\d+)\b", _section, result, flags=re.IGNORECASE)

    def _replace_section_id(match: re.Match[str]) -> str:
        section_id = match.group(0)
        heading = section_labels.get(section_id)
        return f'"{heading}"' if heading else "the relevant section"

    result = SECTION_ID_PATTERN.sub(_replace_section_id, result)
    return result


def humanize_qc_issue_list(
    issues: list[str] | None,
    section_labels: dict[str, str],
) -> list[str]:
    return [humanize_qc_text(issue, section_labels) for issue in issues or []]


def _is_det_check_id(check_id: str | None) -> bool:
    return bool(check_id and check_id.startswith("det_"))


def _tier_for_det_id(check_id: str) -> DetDisplayTier:
    if check_id in STRUCTURE_DET_IDS:
        return "structure"
    if check_id in EVIDENCE_DET_IDS:
        return "evidence"
    return "formatting"


def extract_failed_checks(qc_result: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not qc_result:
        return []

    checks = qc_result.get("checks") or []
    from_checks = [
        check
        for check in checks
        if isinstance(check, dict) and not check.get("passed", True)
    ]
    if from_checks:
        return from_checks

    failed_checks = qc_result.get("failed_checks") or []
    return [
        check
        for check in failed_checks
        if isinstance(check, dict) and not check.get("passed", True)
    ]


def _parse_evidence_headings(evidence: str) -> tuple[str | None, str | None]:
    section_match = re.search(r"Section '([^']+)'", evidence)
    subsection_match = re.search(r"subsection '([^']+)'", evidence)
    return (
        section_match.group(1) if section_match else None,
        subsection_match.group(1) if subsection_match else None,
    )


def _label_from_section_id(
    section_id: str | None,
    section_labels: dict[str, str],
) -> str | None:
    if not section_id:
        return None
    heading = section_labels.get(section_id)
    return f'"{heading}"' if heading else None


def _resolve_structure_missing_labels(
    evidence: str,
    section_labels: dict[str, str],
) -> list[str]:
    if "Missing section ids:" not in evidence:
        return []
    ids = SECTION_ID_PATTERN.findall(evidence)
    return [
        _label_from_section_id(section_id, section_labels) or section_id
        for section_id in ids
    ]


def _build_det_display_item(
    check: dict[str, Any],
    section_labels: dict[str, str],
) -> dict[str, Any]:
    check_id = str(check.get("id") or "")
    tier = _tier_for_det_id(check_id)
    evidence = str(check.get("evidence") or "")
    section_heading, subsection_heading = _parse_evidence_headings(evidence)

    section_label = _label_from_section_id(check.get("section_id"), section_labels)
    if not section_label and section_heading:
        section_label = f'"{section_heading}"'
    if not section_label:
        section_label = "One section"

    subsection_label = f'"{subsection_heading}"' if subsection_heading else None

    if check_id == "det_structure_coverage":
        missing = _resolve_structure_missing_labels(evidence, section_labels)
        if missing:
            joined = ", ".join(missing)
            return {
                "check_id": check_id,
                "section_label": joined,
                "subsection_label": None,
                "user_message": f"Missing planned sections: {joined}.",
                "tier": tier,
            }

    builder = DET_USER_MESSAGE_BUILDERS.get(check_id)
    if builder:
        user_message = builder(section_label, subsection_label)
    else:
        display_section = (
            f"{section_label} → {subsection_label}"
            if subsection_label
            else section_label
        )
        hint = check.get("corrective_hint") or evidence or "Review this section."
        user_message = f"{display_section} — {hint}"

    return {
        "check_id": check_id,
        "section_label": section_label,
        "subsection_label": subsection_label,
        "user_message": user_message,
        "tier": tier,
    }


def _primary_det_tier(items: list[dict[str, Any]]) -> DetDisplayTier:
    if any(item.get("tier") == "evidence" for item in items):
        return "evidence"
    if any(item.get("tier") == "structure" for item in items):
        return "structure"
    return "formatting"


def _title_and_body_for_det_only(
    items: list[dict[str, Any]],
) -> tuple[str, str, str | None]:
    tier = _primary_det_tier(items)
    if tier == "structure":
        return DET_STRUCTURE_TITLE, DET_STRUCTURE_BODY, None
    if tier == "evidence":
        return DET_EVIDENCE_TITLE, DET_EVIDENCE_BODY, None
    return DET_FORMATTING_TITLE, DET_FORMATTING_BODY, FORMATTING_REASSURANCE


def _group_det_items(items: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    return {
        "formatting_items": [
            item for item in items if item.get("tier") == "formatting"
        ],
        "structure_items": [item for item in items if item.get("tier") == "structure"],
        "evidence_items": [item for item in items if item.get("tier") == "evidence"],
    }


def _build_det_summary(items: list[dict[str, Any]]) -> str | None:
    if not items:
        return None
    if len(items) == 1:
        item = items[0]
        where = (
            f"{item['section_label']} → {item['subsection_label']}"
            if item.get("subsection_label")
            else item["section_label"]
        )
        return f"1 item in {where} — see report below."
    return f"{len(items)} formatting or structure items — see report below."


def _det_report_section_label(kind: QcWarningKind, tier: DetDisplayTier) -> str:
    if kind == "mixed":
        if tier == "formatting":
            return "Formatting notes"
        if tier == "structure":
            return "Structure notes"
        return "Teaching evidence notes"
    if tier == "structure":
        return "Missing sections"
    if tier == "evidence":
        return "Sections to review"
    return "Sections to skim"


def build_qc_warning_presentation(
    qc_result: dict[str, Any] | None,
    concept_plan: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if not qc_result:
        return None

    section_labels = build_section_label_map(concept_plan)
    failed = extract_failed_checks(qc_result)
    if not failed:
        return None

    det_failed = [check for check in failed if _is_det_check_id(str(check.get("id")))]
    llm_failed = [
        check for check in failed if not _is_det_check_id(str(check.get("id")))
    ]

    det_items = [_build_det_display_item(check, section_labels) for check in det_failed]
    grouped = _group_det_items(det_items)

    if det_failed and not llm_failed:
        alert_title, alert_body, reassurance = _title_and_body_for_det_only(det_items)
        kind: QcWarningKind = "det_only"
    elif det_failed and llm_failed:
        alert_title, alert_body, reassurance = MIXED_TITLE, MIXED_BODY, None
        kind = "mixed"
    else:
        alert_title, alert_body, reassurance = (
            QC_LLM_FAILED_TITLE,
            QC_LLM_FAILED_BODY,
            None,
        )
        kind = "llm_content"

    primary_tier = _primary_det_tier(det_items) if det_items else "formatting"
    is_formatting_only = (
        kind == "det_only"
        and bool(grouped["formatting_items"])
        and not grouped["structure_items"]
        and not grouped["evidence_items"]
    )

    return {
        "kind": kind,
        "alert_title": alert_title,
        "alert_body": alert_body,
        "det_summary": _build_det_summary(det_items) if det_items else None,
        "reassurance": reassurance,
        "formatting_items": grouped["formatting_items"],
        "structure_items": grouped["structure_items"],
        "evidence_items": grouped["evidence_items"],
        "formatting_list_label": _det_report_section_label(kind, "formatting"),
        "structure_list_label": _det_report_section_label(kind, "structure"),
        "evidence_list_label": _det_report_section_label(kind, "evidence"),
        "det_only_list_label": _det_report_section_label("det_only", primary_tier),
        "is_formatting_only": is_formatting_only,
        "content_issues_label": (
            "Content review items" if kind == "mixed" else "Issues Found"
        ),
    }


def enrich_qc_result_for_client(
    qc_result: dict[str, Any] | None,
    concept_plan: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Attach warning presentation and humanized issue text for mentor UI."""
    if not qc_result or not isinstance(qc_result, dict):
        return qc_result

    enriched = dict(qc_result)
    section_labels = build_section_label_map(concept_plan)

    presentation = build_qc_warning_presentation(enriched, concept_plan)
    if presentation:
        enriched["warning_presentation"] = presentation

    issues = enriched.get("issues")
    if isinstance(issues, list) and issues:
        enriched["humanized_issues"] = humanize_qc_issue_list(issues, section_labels)

    corrective = enriched.get("corrective_instructions")
    if isinstance(corrective, str) and corrective.strip():
        enriched["humanized_corrective_instructions"] = humanize_qc_text(
            corrective,
            section_labels,
        )

    return enriched
