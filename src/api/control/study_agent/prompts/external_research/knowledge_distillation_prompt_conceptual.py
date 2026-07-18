"""Shared instruction skeleton + Conceptual PRESERVE block (design §9.3 / §9.4.3)."""

from src.api.control.study_agent.prompts.external_research.knowledge_distillation_prompt_stem import (
    SHARED_DISTILLATION_SKELETON,
)

_CONCEPTUAL_PRESERVE = """
PRESERVE (extractive-first — copy verbatim wherever possible):
- Definitions of key terms and concepts
- Named theories, models, cases, events, and people — exact names
- Causal or logical reasoning chains as presented (if the source says A
  leads to B leads to C, preserve that order and relationship)
- Dates, figures, and named entities exactly as stated
- Explicit comparisons, contrasts, or distinctions the source draws
- Arguments and any counterarguments or caveats the source itself raises
- Examples the source uses to illustrate a concept (preserve, do not invent
  new ones)
- Stated limitations, exceptions, or edge cases to a claim or theory

Incidental equations or code: if SOURCE_CHUNK contains a displayed equation,
formula, fenced code block, or complete code snippet (even when the topic is
primarily conceptual), copy that material VERBATIM into knowledge_notes —
do not paraphrase an equation into prose or summarize code as a signature list.

Do not add interpretive framing the source doesn't contain (e.g. "this is
significant because..." unless the source itself says why it's significant).
Do not resolve ambiguity the source leaves open — preserve it as ambiguous.
"""

CONCEPTUAL_DISTILLATION_PROMPT = SHARED_DISTILLATION_SKELETON + _CONCEPTUAL_PRESERVE
