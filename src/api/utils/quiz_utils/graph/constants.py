"""Constants for the quiz generation LangGraph.

Shared retry limits and routing mode sets used by graph nodes, conditional
edges, and ``resume_router``. Changing these values affects both in-graph
loops (``quiz_generator`` ↔ ``deterministic_validate`` / ``quality_check``)
and cross-request resume behavior.
"""

from __future__ import annotations

# Max structural-validation retries before persisting a failed draft (gen loop).
MAX_GEN_ATTEMPTS = 3
# Max QC evaluation retries (includes infra-error re-runs without regeneration).
MAX_QC_ATTEMPTS = 3
# QC routing modes that trigger surgical LLM retries in quiz_generator_node.
QUESTION_RETRY_MODES = frozenset(
    {"question_patch", "question_insert", "question_patch_then_insert"}
)
