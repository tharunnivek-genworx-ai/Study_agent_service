"""Topic/subtopic resolution for Tavily search queries (design §4 / A.3)."""

from __future__ import annotations

import re

_GENERIC_TITLE_PATTERNS = [
    r"^module\s*\d+$",
    r"^week\s*\d+$",
    r"^unit\s*\d+$",
    r"^chapter\s*\d+$",
    r"^section\s*\d+$",
    r"^part\s*\d+$",
    r"^lesson\s*\d+$",
    r"^day\s*\d+$",
    r"^\d+(\.\d+)*$",  # pure numeric or dotted numbering like "1.2.3"
]


def _is_generic_title(title: str) -> bool:
    normalized = title.strip().lower()
    if len(normalized) < 3:
        return True
    return any(re.match(pattern, normalized) for pattern in _GENERIC_TITLE_PATTERNS)


def resolve_research_query(
    node_title: str,
    ancestor_titles_nearest_first: list[str],
) -> dict[str, str | None]:
    """Build search query from node title + nearest non-generic ancestors.

    ``ancestor_titles_nearest_first``: immediate parent outward to root, e.g.
    for Root > FastAPI > Deployment > Uvicorn with node_title "Uvicorn":
    ``["Deployment", "FastAPI", "Root"]``.
    """
    non_generic = [
        title for title in ancestor_titles_nearest_first if not _is_generic_title(title)
    ]

    if len(non_generic) == 0:
        query = node_title
        topic, subtopic = None, node_title
    elif len(non_generic) <= 2:
        # up to 3 total levels: subtopic + up to 2 ancestor levels
        levels = list(reversed(non_generic[:2]))  # outer -> inner order
        query = " ".join([*levels, node_title])
        topic, subtopic = " ".join(levels), node_title
    else:
        # deep tree: nearest non-generic ancestor only, not the root
        nearest = non_generic[0]
        query = f"{nearest} {node_title}"
        topic, subtopic = nearest, node_title

    return {
        "search_query": query.strip(),
        "resolved_topic": topic,
        "resolved_subtopic": subtopic,
    }
