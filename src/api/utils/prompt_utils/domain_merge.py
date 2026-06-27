"""Domain-aware prompt block selection for token-efficient assembly."""

from __future__ import annotations

VALID_DOMAINS = frozenset({"STEM", "Programming", "Conceptual", "Mixed"})

_ALL_DOMAINS = frozenset({"STEM", "Programming", "Conceptual", "Mixed"})


def normalize_domain(domain: str | None) -> str:
    """Strip whitespace; return empty string if missing or unknown."""
    value = str(domain or "").strip()
    if value in VALID_DOMAINS:
        return value
    return ""


def domains_to_include(domain: str | None) -> frozenset[str]:
    """Return which domain keys should be merged for the given classification."""
    normalized = normalize_domain(domain)
    if not normalized or normalized == "Mixed":
        return _ALL_DOMAINS
    return frozenset({normalized})


def merge_domain_blocks(
    blocks: dict[str, str],
    domain: str | None,
    *,
    order: tuple[str, ...] = ("STEM", "Programming", "Conceptual", "Mixed"),
    header: str = "",
    separator: str = "\n\n",
) -> str:
    """Concatenate selected blocks in stable order; skip missing keys."""
    included = domains_to_include(domain)
    parts: list[str] = []
    if header:
        parts.append(header)
    for key in order:
        if key in included and key in blocks:
            parts.append(blocks[key])
    return separator.join(parts)


def classification_block(
    *,
    domain: str | None,
    when_unknown: str,
    when_known: str,
) -> str:
    """Return full classify text when domain empty; short stub when known."""
    normalized = normalize_domain(domain)
    if not normalized:
        return when_unknown
    return when_known.replace("<domain>", normalized)
