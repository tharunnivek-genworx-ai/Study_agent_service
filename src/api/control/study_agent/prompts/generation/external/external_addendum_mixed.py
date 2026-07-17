"""Mixed external-mode addendum: apply domain rules section-locally from notes."""

from src.api.control.study_agent.prompts.generation.external.shared_external_policy import (
    SHARED_EXTERNAL_POLICY,
)

_MIXED_FROM_NOTES = """
MIXED — WHAT TO PULL FROM RESEARCH NOTES
Classify each section by what it actually teaches, then apply the matching
STEM / Programming / Conceptual notes rules for that section only:
- STEM-classified sections: prefer equations, units, years, named experiments,
  and derivation steps from notes into formula_blocks
- Programming-classified sections: prefer full code, signatures, and lifecycle
  detail from notes into code_blocks; do not rename APIs from notes
- Conceptual-classified sections: prefer named cases, dates, and causal chains
  from notes; no fabricated orgs/stats that contradict notes

Never paraphrase equations into prose, invent code for a conceptual section, or
carry code_blocks / formula_blocks into a section whose content does not call
for them. When notes omit a concept, invent full material under that section's
domain standard to meet the depth_gate.
"""

EXTERNAL_ADDENDUM_MIXED = SHARED_EXTERNAL_POLICY + _MIXED_FROM_NOTES
