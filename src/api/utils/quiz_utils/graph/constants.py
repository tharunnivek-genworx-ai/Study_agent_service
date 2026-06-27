"""Constants for the quiz generation LangGraph."""

from __future__ import annotations

MAX_GEN_ATTEMPTS = 3
MAX_QC_ATTEMPTS = 3
QUESTION_RETRY_MODES = frozenset(
    {"question_patch", "question_insert", "question_patch_then_insert"}
)
