"""Rule-based residual cleanup — no LLM (design §7 / A.6)."""

from __future__ import annotations

import re
from typing import Any

# Heading-only section starts: cut from the matching line through EOF.
# Ambiguous titles (e.g. "References") only truncate in the latter half so
# mid-article mentions like "DOM references" are not treated as section heads.
_SECTION_TRUNCATE_SPECS: list[tuple[str, bool]] = [
    # (pattern, latter_half_only)
    # Bibliography / Works cited are almost always trailing; still allow early cut.
    (r"^\s*Bibliography\s*$", False),
    (r"^\s*Works cited\s*$", False),
    # Ambiguous / often mid-article in some domains — latter half only.
    (r"^\s*References\s*$", True),
    (r"^\s*Further reading\s*$", True),
    (r"^\s*External links\s*$", True),
    (r"^\s*See also\s*$", True),
    # EBSCO-style related chrome (sometimes concatenated on one line)
    (r"^\s*More Like This\s*$", False),
    (r"^\s*Related Articles(\s*\(\d+\))?\s*$", False),
    (r"^\s*More Like This\s*Related Articles.*$", False),
    # Course / enrollment chrome
    (r"^\s*Related courses and paths\s*$", False),
    (r"^\s*Our learners work at\s*$", False),
    (r"^\s*Looking for something else\??\s*$", False),
    (r"^\s*Earn a certificate of completion\s*$", False),
    (r"^\s*Certificate of completion\s*$", False),
    (r"^\s*.*\bcourse ratings and reviews\s*$", False),
]

_COMPILED_SECTION_TRUNCATE = [
    (re.compile(pattern, re.IGNORECASE), latter_half_only)
    for pattern, latter_half_only in _SECTION_TRUNCATE_SPECS
]

_BOILERPLATE_LINE_PATTERNS = [
    r"^\s*(edit this page|improve this page|edit on github).*$",
    r"^\s*was this (page|article) helpful\??.*$",
    r"^\s*(share this|follow us on).*$",
    r"^\s*(subscribe|sign up) (to|for) our newsletter.*$",
    r"^\s*(home|docs?)\s*>\s*.*$",  # breadcrumb-style lines
    r"^\s*table of contents\s*$",
    r"^\s*(previous|next)\s*(page|article|chapter)?\s*$",
    r"^\s*©\s*\d{4}.*$",  # copyright lines
    r"^\s*all rights reserved\.?\s*$",
    r"^\s*\d+\s+min(ute)?s?\s+read\s*$",  # "5 min read"
    r"^\s*posted (on|by).*$",
    r"^\s*last updated:?.*$",
    # Legacy / stale-docs banners
    r"^\s*These docs are old.*$",
    r"^\s*Go to react\.dev.*$",
    r"^\s*Looking for something else\??\s*$",
    # Course / enrollment marketing
    r"^\s*.*\blearners enrolled\b.*$",
    r"^\s*-\s*Skill level\b.*$",
    r"^\s*-\s*Time to complete\b.*$",
    r"^\s*.*\bCertificate of completion\b.*$",
    r"^\s*Unlock additional features\b.*$",
    r"^\s*Join over \d+ million learners\b.*$",
    # Star-rating chrome
    r"^\s*-\s*[1-5]\s+stars?\s*$",
    # Wiki series / separator chrome only — do NOT strip arbitrary |a|b|c| tables
    # (those may be teaching comparison tables).
    r"^\s*\|\s*Part of a series\b.*$",
    r"^\s*\|[^|\n]{1,60}\|\s*$",  # single-cell short rows like "| Quantum mechanics |"
    r"^\s*\|-+\|?\s*$",
    r"^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$",
]

_COMPILED_PATTERNS = [
    re.compile(pattern, re.IGNORECASE) for pattern in _BOILERPLATE_LINE_PATTERNS
]

# Wiki extracts often drop "References" / "See also" headings; detect citation runs instead.
_CITATION_MARKERS = re.compile(
    r"\bISBN\b|\bdoi:\s*\d|Bibcode:|\bRetrieved\b|\barXiv:",
    re.IGNORECASE,
)
_CITATION_AUTHOR_YEAR = re.compile(r"\(\d{4}(?:-\d{2}-\d{2})?\)\.")
_SEE_ALSO_TITLE_BLURB = re.compile(r"^\s*-\s+.+\s+[–—]\s+\S")
# Verbs / predicates common in teaching bullets — never treat as See-also titles.
_TEACHING_BULLET_MARKERS = re.compile(
    r"\b("
    r"is|are|was|were|be|been|being|have|has|had|"
    r"do|does|did|can|could|should|must|may|might|"
    r"use|uses|using|used|create|creates|creating|write|writes|writing|"
    r"eliminate|eliminates|manage|manages|run|runs|running|call|calls|"
    r"let|lets|enable|enables|learn|learns|implement|implements|"
    r"return|returns|need|needs|needed|diffract|diffracts|exhibit|exhibits|"
    r"show|shows|maintain|maintains|fetch|fetches|help|helps|helped|"
    r"explain|explains|explained|describe|describes|provide|provides|"
    r"allow|allows|require|requires|include|includes|contain|contains"
    r")\b",
    re.IGNORECASE,
)
_MIN_CITATION_RUN = 3


def _is_citation_line(line: str) -> bool:
    """Heuristic for Wikipedia-style bibliography / external-link bullets."""
    stripped = line.strip()
    if not stripped.startswith("-"):
        return False
    if _CITATION_MARKERS.search(stripped):
        return True
    return bool(_CITATION_AUTHOR_YEAR.search(stripped))


def _is_see_also_line(line: str) -> bool:
    """Strict wiki 'See also' topic-link bullets (not ordinary teaching bullets).

    Matches:
    - ``- Topic – short blurb`` (en/em dash), or
    - short Capitalized title-only rows without teaching verbs / ``:`` / ``=``
    """
    stripped = line.strip()
    if not stripped.startswith("-"):
        return False
    if _is_citation_line(stripped):
        return False
    if len(stripped) > 120:
        return False
    if _SEE_ALSO_TITLE_BLURB.match(stripped):
        return True
    # Bare wiki title: "- Uncertainty principle" — not "- Write function components"
    if re.search(r"[:=`]", stripped):
        return False
    if _TEACHING_BULLET_MARKERS.search(stripped):
        return False
    return bool(re.match(r"^\s*-\s+[A-Z]", stripped))


def _remainder_is_trailing_chrome(lines: list[str], start: int) -> bool:
    """True if lines[start:] are only blanks, citations, or see-also bullets."""
    for line in lines[start:]:
        if not line.strip():
            continue
        if _is_citation_line(line) or _is_see_also_line(line):
            continue
        return False
    return True


def _truncate_trailing_sections(text: str) -> str:
    """Cut from the first qualifying trailing-section heading through EOF."""
    if not text:
        return text

    lines = text.split("\n")
    total_len = len(text)
    char_pos = 0

    for i, line in enumerate(lines):
        for pattern, latter_half_only in _COMPILED_SECTION_TRUNCATE:
            if not pattern.match(line):
                continue
            if latter_half_only and char_pos < total_len / 2:
                continue
            return "\n".join(lines[:i]).rstrip("\n")
        char_pos += len(line) + 1  # +1 for the newline (except final line; approx OK)

    return text


def _truncate_wiki_trailing_lists(text: str) -> str:
    """Cut heading-less wiki See also + References bullet runs in the latter half.

    When extractors drop section titles, Wikipedia still leaves a dense citation
    bullet dump at the end. If >=3 consecutive citation-like bullets appear in
    the latter half **and the remainder through EOF is only citations /
    see-also chrome**, truncate from that run (walking back only strict
    see-also topic links, never across blank lines) through EOF.

    Mid-article citation-like lists followed by more body are left intact.
    """
    if not text:
        return text

    lines = text.split("\n")
    total_len = len(text)
    line_starts: list[int] = []
    pos = 0
    for line in lines:
        line_starts.append(pos)
        pos += len(line) + 1

    i = 0
    while i < len(lines):
        if line_starts[i] < total_len / 2 or not _is_citation_line(lines[i]):
            i += 1
            continue

        run_start = i
        citation_count = 0
        j = i
        while j < len(lines):
            if not lines[j].strip():
                j += 1
                continue
            if _is_citation_line(lines[j]):
                citation_count += 1
                j += 1
                continue
            break

        # Only truncate when this run is true trailing chrome (nothing
        # substantive after it through EOF).
        if citation_count >= _MIN_CITATION_RUN and _remainder_is_trailing_chrome(
            lines, run_start
        ):
            cut = run_start
            k = run_start - 1
            while k >= 0:
                if not lines[k].strip():
                    # Do not walk across blank lines into earlier body sections.
                    break
                if _is_see_also_line(lines[k]) and line_starts[k] >= total_len / 2:
                    cut = k
                    k -= 1
                    continue
                break
            return "\n".join(lines[:cut]).rstrip("\n")

        i = j if j > i else i + 1

    return text


def clean_extracted_text(text: str) -> str:
    """Strip residual boilerplate and trailing chrome; never summarizes or invents."""
    text = _truncate_trailing_sections(text)
    text = _truncate_wiki_trailing_lists(text)

    lines = text.split("\n")
    kept_lines = [
        line
        for line in lines
        if not any(pattern.match(line) for pattern in _COMPILED_PATTERNS)
    ]

    cleaned = "\n".join(kept_lines)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    cleaned = re.sub(
        r"^\s*\[\d+\]:\s*https?://\S+\s*$",
        "",
        cleaned,
        flags=re.MULTILINE,
    )
    # Trim blank lines only — do not rstrip the last content line's spaces.
    parts = cleaned.split("\n")
    while parts and not parts[0].strip():
        parts.pop(0)
    while parts and not parts[-1].strip():
        parts.pop()
    return "\n".join(parts)


def distill_extracted_pages(
    extracted_pages: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    cleaned_pages: list[dict[str, Any]] = []
    for page in extracted_pages:
        raw = str(page.get("raw_text") or "")
        cleaned_pages.append(
            {
                "url": page.get("url"),
                "cleaned_text": clean_extracted_text(raw),
            }
        )
    return cleaned_pages
