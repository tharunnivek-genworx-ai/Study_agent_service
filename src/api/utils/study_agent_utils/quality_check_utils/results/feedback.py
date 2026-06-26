"""QC feedback formatting for generator retries."""

from __future__ import annotations

from typing import Any


def format_qc_feedback(qc_result: dict[str, Any]) -> str:
    """Build actionable feedback for the writer retry prompt."""
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
