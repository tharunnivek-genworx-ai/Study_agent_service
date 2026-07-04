"""QC feedback formatting for generator retries.

Two feedback channels (by design):
  - **section_patch / insert:** structured ``qc_section_failures`` →
    ``section_rework_prompt`` (``<sections_to_fix>`` JSON). Not this module.
  - **full_regeneration:** flat text from ``format_qc_feedback`` →
    ``<quality_check_feedback>`` in ``generation_prompt``.

``format_qc_feedback`` is also stored as ``qc_feedback`` in graph state on QC fail
and re-derived from DB ``qc_result`` for improve/regenerate hydration. Both are
logged in ``05_qc_result.json`` via ``build_qc_retry_context`` (audit trail).
"""

from __future__ import annotations

from typing import Any


def format_qc_feedback(qc_result: dict[str, Any]) -> str:
    """Build flat text feedback for full-regeneration retry prompts.

    Formats failed checks (severity, category, id, question, evidence, hint),
    optional ``issues`` list, and ``corrective_instructions`` from the QC LLM.

    Args:
        qc_result: ``build_final_qc_result`` output (uses ``failed_checks`` or
            derives from ``checks`` where ``passed`` is false).

    Returns:
        Multi-paragraph string for ``state["qc_feedback"]`` / ``<quality_check_feedback>``.
    """
    parts: list[str] = []

    failed_checks: list[dict[str, Any]] = qc_result.get("failed_checks", [])
    if not failed_checks:
        checks = qc_result.get("checks", [])
        if isinstance(checks, list):
            failed_checks = [
                c for c in checks if isinstance(c, dict) and not c.get("passed", True)
            ]

    if failed_checks:
        check_lines = []
        for c in failed_checks:
            sev = c.get("severity", "?")
            cat = c.get("category", "?")
            cid = c.get("id", "?")
            question = c.get("question", "")
            evidence = c.get("evidence", "")
            hint = c.get("corrective_hint", "")
            line = f"  - [{sev}] {cat}/{cid}"
            if question:
                line += f": {question}"
            if evidence:
                sep = " — " if question else ": "
                line += f"{sep}{evidence}"
            if hint:
                line += f" → {hint}"
            check_lines.append(line)
        parts.append("Failed Checks:\n" + "\n".join(check_lines))

    issues = qc_result.get("issues", [])
    if issues:
        issue_lines = [f"  - {issue}" for issue in issues]
        parts.append("Issues Found:\n" + "\n".join(issue_lines))

    corrective = qc_result.get("corrective_instructions", "")
    if corrective:
        parts.append(f"Corrective Instructions: {corrective}")

    return "\n\n".join(parts)
