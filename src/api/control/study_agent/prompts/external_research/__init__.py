"""Prompt text for external research LLM nodes — design doc verbatim."""

from src.api.control.study_agent.prompts.external_research.cross_website_merge_prompt import (
    CROSS_WEBSITE_MERGE_PROMPT,
)
from src.api.control.study_agent.prompts.external_research.knowledge_distillation_prompt_conceptual import (
    CONCEPTUAL_DISTILLATION_PROMPT,
)
from src.api.control.study_agent.prompts.external_research.knowledge_distillation_prompt_mixed import (
    MIXED_DISTILLATION_PROMPT,
)
from src.api.control.study_agent.prompts.external_research.knowledge_distillation_prompt_programming import (
    PROGRAMMING_DISTILLATION_PROMPT,
)
from src.api.control.study_agent.prompts.external_research.knowledge_distillation_prompt_stem import (
    STEM_DISTILLATION_PROMPT,
)
from src.api.control.study_agent.prompts.external_research.website_reduction_prompt import (
    WEBSITE_REDUCTION_PROMPT,
)

DISTILLATION_PROMPTS_BY_DOMAIN: dict[str, str] = {
    "STEM": STEM_DISTILLATION_PROMPT,
    "Programming": PROGRAMMING_DISTILLATION_PROMPT,
    "Conceptual": CONCEPTUAL_DISTILLATION_PROMPT,
    "Mixed": MIXED_DISTILLATION_PROMPT,
}

__all__ = [
    "CONCEPTUAL_DISTILLATION_PROMPT",
    "CROSS_WEBSITE_MERGE_PROMPT",
    "DISTILLATION_PROMPTS_BY_DOMAIN",
    "MIXED_DISTILLATION_PROMPT",
    "PROGRAMMING_DISTILLATION_PROMPT",
    "STEM_DISTILLATION_PROMPT",
    "WEBSITE_REDUCTION_PROMPT",
]
