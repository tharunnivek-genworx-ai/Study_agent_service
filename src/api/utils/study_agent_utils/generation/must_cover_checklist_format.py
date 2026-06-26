"""Format must_cover checklist items for LLM user messages — no heavy imports."""

from __future__ import annotations

from typing import Any


def checklist_section_id(item: dict[str, Any]) -> str:
    """Document section id for a must_cover item (topic_split id or legacy mc id)."""
    section_id = str(item.get("section_id", "")).strip()
    if section_id:
        return section_id
    return str(item.get("id", "")).strip()


def format_must_cover_checklist_line(item: dict[str, Any]) -> str:
    """One bullet line for must_cover items in generator/QC user messages."""
    section_id = checklist_section_id(item)
    return (
        f"  - [{item.get('priority', 'required')}] {item.get('id', '')}"
        f" (section_id: {section_id}): {item.get('concept', '')} — {item.get('requirement', '')}"
        + (f" | depth_gate: {item['depth_gate']}" if item.get("depth_gate") else "")
    )
