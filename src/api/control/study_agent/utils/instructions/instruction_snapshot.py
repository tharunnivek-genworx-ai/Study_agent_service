"""Effective instruction markers embedded in study material prompt snapshots."""

from __future__ import annotations

_MARKER_START = "[EFFECTIVE_INSTRUCTION_AT_GENERATION]\n"
_MARKER_END = "\n[/EFFECTIVE_INSTRUCTION_AT_GENERATION]"


def embed_effective_instruction_snapshot(
    prompt_snapshot: str | None,
    effective_instruction: str | None,
) -> str | None:
    """Prefix prompt_snapshot with the instruction used at generation time."""
    if not prompt_snapshot:
        return prompt_snapshot
    instruction = (effective_instruction or "").strip()
    if not instruction:
        return prompt_snapshot
    return f"{_MARKER_START}{instruction}{_MARKER_END}\n\n{prompt_snapshot}"


def extract_effective_instruction_snapshot(prompt_snapshot: str | None) -> str | None:
    """Read the generation-time effective instruction from a stored prompt snapshot."""
    if not prompt_snapshot:
        return None
    start = prompt_snapshot.find(_MARKER_START)
    if start == -1:
        return None
    end = prompt_snapshot.find(_MARKER_END, start)
    if end == -1:
        return None
    return prompt_snapshot[start + len(_MARKER_START) : end].strip() or None
