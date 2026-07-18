"""Programming external-mode addendum: prefer full code/signatures from notes."""

from src.api.control.study_agent.prompts.generation.external.shared_external_policy import (
    SHARED_EXTERNAL_POLICY,
)

_PROGRAMMING_FROM_NOTES = """
PROGRAMMING — WHAT TO PULL FROM RESEARCH NOTES
When notes cover a concept for this section, prefer and adapt from notes:
- Complete code examples into code_blocks when present (trim only for readability;
  do not replace with a different invented demo)
- Imports, signatures, parameter names/types, cleanup, and dependency/lifecycle notes
- Execution-trace detail in the explanation field when notes describe behaviour
- Exact API, function, and type names from the notes — do not rename them

When notes omit the concept, invent full Programming teaching material (explanation,
runnable example, execution trace) to meet the depth_gate. Never substitute a
parallel library, helper, or endpoint for an API the notes already teach.
"""

EXTERNAL_ADDENDUM_PROGRAMMING = SHARED_EXTERNAL_POLICY + _PROGRAMMING_FROM_NOTES
