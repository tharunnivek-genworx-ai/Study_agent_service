"""Shared hint completeness helpers for quiz mentor UI."""

from __future__ import annotations


def compute_hints_status(questions: list) -> str:
    """
    "none"     — no active question has any hint populated
    "partial"  — some but not all active questions have all three hints
    "complete" — every active question has hint_1, hint_2, and hint_3 populated
    """
    if not questions:
        return "none"
    complete = [
        q
        for q in questions
        if q.hint_1 is not None and q.hint_2 is not None and q.hint_3 is not None
    ]
    if len(complete) == len(questions):
        return "complete"
    if len(complete) == 0:
        return "none"
    return "partial"
