"""Shared instruction skeleton + Programming PRESERVE block (design §9.3 / §9.4.2)."""

from src.api.control.study_agent.prompts.external_research.knowledge_distillation_prompt_stem import (
    SHARED_DISTILLATION_SKELETON,
)

_PROGRAMMING_PRESERVE = """
PRESERVE (extractive-first — copy verbatim wherever possible):
- Every complete code block, import, and signature exactly as written
- For each major API, type, or hook the chunk demonstrates: keep 1–2 full
  runnable examples from the source (including body, imports, and cleanup when
  present) — do NOT reduce them to a syntax-only catalog of names/signatures
- Function/method names, parameter names, types, defaults, required/optional
- CLI commands and flags exactly as written
- Configuration keys, environment variable names, and file paths
- Version numbers and compatibility notes (e.g. "requires Python 3.10+")
- Behavior descriptions including documented side effects
- Error messages or exceptions explicitly named in the source
- Cleanup, dependency, and lifecycle semantics when stated
- Comparisons between approaches, libraries, or patterns
- Constraints and limitations explicitly stated (e.g. "not thread-safe",
  "deprecated since v2")

Special rule for code: never reformat, "improve," rename variables in, or
complete a truncated code block from the source. Reproduce it exactly as
given, even partial, and mark continues_next_chunk = true if a code block
is cut off by the chunk boundary. A taxonomy or one-line signature list is
not a substitute for full examples that appear in SOURCE_CHUNK.
"""

PROGRAMMING_DISTILLATION_PROMPT = SHARED_DISTILLATION_SKELETON + _PROGRAMMING_PRESERVE
