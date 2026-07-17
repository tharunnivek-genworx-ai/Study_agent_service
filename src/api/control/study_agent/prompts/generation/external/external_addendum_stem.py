"""STEM external-mode addendum: prefer equations, years, experiments from notes."""

from src.api.control.study_agent.prompts.generation.external.shared_external_policy import (
    SHARED_EXTERNAL_POLICY,
)

_STEM_FROM_NOTES = """
STEM — WHAT TO PULL FROM RESEARCH NOTES
When notes cover a concept for this section, prefer and adapt from notes:
- Equations, notation, and units — keep them exact; place them in formula_blocks
- Years, dates, and named laws, theorems, or experiments
- Worked numeric or algebraic steps and intermediate results
- Stated assumptions, constraints, and boundary conditions

When notes omit the concept, invent full STEM teaching material (formal statement,
derivation or proof where appropriate, worked example, assumptions) to meet the
depth_gate. Never replace a note-backed equation or derivation with a different
parallel demo.
"""

EXTERNAL_ADDENDUM_STEM = SHARED_EXTERNAL_POLICY + _STEM_FROM_NOTES
