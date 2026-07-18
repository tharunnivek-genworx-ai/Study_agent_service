"""Conceptual external-mode addendum: prefer named cases and causal chains from notes."""

from src.api.control.study_agent.prompts.generation.external.shared_external_policy import (
    SHARED_EXTERNAL_POLICY,
)

_CONCEPTUAL_FROM_NOTES = """
CONCEPTUAL — WHAT TO PULL FROM RESEARCH NOTES
When notes cover a concept for this section, prefer and adapt from notes:
- Exact names of people, organisations, laws, events, theories, and cases
- Dates and figures as stated
- Causal or argumentative order (precondition → trigger → mechanism → outcome)
- Source examples and named cases — rewrite into lesson prose; do not invent a
  different parallel case for a concept the notes already illustrate

When notes omit the concept, invent full Conceptual teaching material (definition,
mechanism, named real-world case) to meet the depth_gate. Do not fabricate
organisations, statistics, or outcomes that contradict the notes.
"""

EXTERNAL_ADDENDUM_CONCEPTUAL = SHARED_EXTERNAL_POLICY + _CONCEPTUAL_FROM_NOTES
