"""Shared instruction skeleton + Mixed PRESERVE block (design §9.3 / §9.4.4)."""

from src.api.control.study_agent.prompts.external_research.knowledge_distillation_prompt_stem import (
    SHARED_DISTILLATION_SKELETON,
)

_MIXED_PRESERVE = """
PRESERVE (extractive-first — copy verbatim wherever possible):
- Definitions of terms and concepts
- Factual claims, figures, dates, and named entities
- Equations, formulae, or numerical data — preserved verbatim (full form,
  not a prose restatement)
- Code snippets or technical syntax — preserved verbatim (full blocks when
  present, not signature-only catalogs)
- Named theories, models, cases, laws, or algorithms
- Causal or logical reasoning chains as presented in the source
- Explicit comparisons, contrasts, and distinctions
- Examples the source itself uses
- Stated constraints, assumptions, limitations, or caveats
- Tables of data or parameters

Dual-precision rule: this topic may blend technical and conceptual material —
do not force content into one style. If a passage is mathematical, preserve it
with the precision you'd use for a STEM source (exact equations/units). If a
passage is conceptual, preserve it with the precision you'd use for a
conceptual source (exact causal claims, named entities). Never collapse an
equation into prose, never invent code for a conceptual passage, and never
turn a code block into a one-line signature summary.
"""

MIXED_DISTILLATION_PROMPT = SHARED_DISTILLATION_SKELETON + _MIXED_PRESERVE
