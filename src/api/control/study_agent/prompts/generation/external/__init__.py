"""Domain-specific external-mode generation addenda (prefer notes + invent-for-gaps)."""

from __future__ import annotations

from src.api.control.study_agent.prompts.generation.external.external_addendum_conceptual import (
    EXTERNAL_ADDENDUM_CONCEPTUAL,
)
from src.api.control.study_agent.prompts.generation.external.external_addendum_mixed import (
    EXTERNAL_ADDENDUM_MIXED,
)
from src.api.control.study_agent.prompts.generation.external.external_addendum_programming import (
    EXTERNAL_ADDENDUM_PROGRAMMING,
)
from src.api.control.study_agent.prompts.generation.external.external_addendum_stem import (
    EXTERNAL_ADDENDUM_STEM,
)
from src.api.control.study_agent.prompts.generation.external.shared_external_policy import (
    SHARED_EXTERNAL_POLICY,
)
from src.api.utils.prompt_utils.domain_merge import normalize_domain

EXTERNAL_ADDENDA_BY_DOMAIN: dict[str, str] = {
    "STEM": EXTERNAL_ADDENDUM_STEM,
    "Programming": EXTERNAL_ADDENDUM_PROGRAMMING,
    "Conceptual": EXTERNAL_ADDENDUM_CONCEPTUAL,
    "Mixed": EXTERNAL_ADDENDUM_MIXED,
}


def resolve_external_addendum(domain: str | None) -> str:
    """Return the external addendum for domain; unknown/empty falls back to Mixed."""
    key = normalize_domain(domain) or "Mixed"
    return EXTERNAL_ADDENDA_BY_DOMAIN.get(key, EXTERNAL_ADDENDUM_MIXED)


__all__ = [
    "EXTERNAL_ADDENDA_BY_DOMAIN",
    "EXTERNAL_ADDENDUM_CONCEPTUAL",
    "EXTERNAL_ADDENDUM_MIXED",
    "EXTERNAL_ADDENDUM_PROGRAMMING",
    "EXTERNAL_ADDENDUM_STEM",
    "SHARED_EXTERNAL_POLICY",
    "resolve_external_addendum",
]
