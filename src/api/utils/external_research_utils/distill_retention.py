"""High-risk content retention heuristics for knowledge distillation retry.

Detects fenced/complete code and equation-like material in SOURCE_CHUNK and
checks whether distilled notes still contain that material. Used to trigger
and score content-retention retries when length-only checks are insufficient.
"""

from __future__ import annotations

import re

_FENCED_CODE_RE = re.compile(r"```[\s\S]*?```")
_DISPLAY_EQ_RE = re.compile(
    r"\$\$[\s\S]+?\$\$|"
    r"\\\[[\s\S]+?\\\]|"
    r"\\begin\{(?:equation\*?|align\*?|eqnarray\*?|displaymath)\}"
    r"[\s\S]+?"
    r"\\end\{(?:equation\*?|align\*?|eqnarray\*?|displaymath)\}",
)
# Lines that look like displayed relations / formulas (not prose).
_EQ_LINE_RE = re.compile(
    r"(?:"
    r"[A-Za-z\\][A-Za-z0-9_\\^{}\s]*\s*[=≈≡≤≥]\s*[^\n]{2,80}"
    r"|"
    r"\\(?:frac|sum|int|partial|nabla|mathrm|mathbf)\b[^\n]*"
    r")"
)
_CODEISH_LINE_RE = re.compile(
    r"^\s*(?:"
    r"def |class |function |async def |import |from |const |let |var |"
    r"public |private |protected |return |#include |package |"
    r"fn |impl |use |console\.|System\.|"
    r"[@#]?\w+\([^)]*\)\s*\{|"
    r".*[;{}]\s*$"
    r")",
    re.MULTILINE,
)


def _normalize_for_match(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def _significant_lines(block: str, *, min_len: int = 8) -> list[str]:
    lines: list[str] = []
    for raw in block.splitlines():
        line = raw.strip()
        if len(line) >= min_len and not set(line) <= {"`", "-", "=", "*", " "}:
            lines.append(line)
    return lines


def extract_high_risk_fragments(chunk: str) -> list[str]:
    """Extract fenced code, display equations, and equation-like lines from chunk."""
    if not chunk or not chunk.strip():
        return []

    fragments: list[str] = []
    seen: set[str] = set()

    def _add(raw: str) -> None:
        frag = raw.strip()
        if len(frag) < 4:
            return
        key = _normalize_for_match(frag)
        if key in seen:
            return
        seen.add(key)
        fragments.append(frag)

    for match in _FENCED_CODE_RE.finditer(chunk):
        _add(match.group(0))

    for match in _DISPLAY_EQ_RE.finditer(chunk):
        _add(match.group(0))

    # Equation-like lines outside already-captured display blocks.
    remainder = _FENCED_CODE_RE.sub("\n", chunk)
    remainder = _DISPLAY_EQ_RE.sub("\n", remainder)
    for match in _EQ_LINE_RE.finditer(remainder):
        line = match.group(0).strip()
        # Skip ordinary prose with equals (e.g. "X is equal to Y because...").
        if len(line.split()) > 18:
            continue
        if line.lower().startswith(("note that", "this means", "which means")):
            continue
        _add(line)

    return fragments


def _has_multiline_codeish_block(chunk: str) -> bool:
    """True when consecutive code-ish lines suggest an unfenced code block."""
    codeish_runs = 0
    max_run = 0
    for line in chunk.splitlines():
        stripped = line.strip()
        if not stripped:
            codeish_runs = 0
            continue
        if _CODEISH_LINE_RE.match(line) or (
            len(stripped) >= 12
            and ("{" in stripped or stripped.endswith((";", "{", "}")))
            and not stripped.endswith(".")
        ):
            codeish_runs += 1
            max_run = max(max_run, codeish_runs)
        else:
            codeish_runs = 0
    return max_run >= 3


def source_has_high_risk_content(chunk: str) -> bool:
    """True if SOURCE_CHUNK contains fenced/code-ish or equation-like material."""
    if extract_high_risk_fragments(chunk):
        return True
    return _has_multiline_codeish_block(chunk)


def _fragment_present_in_notes(fragment: str, notes_norm: str) -> bool:
    """A fragment is retained when enough of its significant lines appear in notes."""
    lines = _significant_lines(fragment)
    if not lines:
        # Short fragment (e.g. ``F = k*q``) — require whole fragment.
        return _normalize_for_match(fragment) in notes_norm

    hits = 0
    for line in lines:
        if _normalize_for_match(line) in notes_norm:
            hits += 1
    # Require majority of significant lines (at least one).
    return hits >= max(1, (len(lines) + 1) // 2)


def high_risk_gap_count(chunk: str, notes: str) -> int:
    """Count high-risk fragments from chunk that are absent from notes.

    Also counts +1 when the source has an unfenced multiline code-ish block and
    notes lack code-like markers (braces / def / function / import).
    """
    notes_norm = _normalize_for_match(notes or "")
    missing = 0
    for frag in extract_high_risk_fragments(chunk):
        if not _fragment_present_in_notes(frag, notes_norm):
            missing += 1

    if _has_multiline_codeish_block(chunk):
        code_markers = ("```", "def ", "function ", "import ", "{", "};", "=>")
        if not any(marker in notes_norm for marker in code_markers):
            # Avoid double-counting when fenced fragments already cover the block.
            if not any("```" in f for f in extract_high_risk_fragments(chunk)):
                missing += 1

    return missing


def notes_missing_high_risk(chunk: str, notes: str) -> bool:
    """True when source has high-risk content that notes omit."""
    if not source_has_high_risk_content(chunk):
        return False
    return high_risk_gap_count(chunk, notes) > 0


# Public aliases matching plan naming (leading underscore style used by callers).
_source_has_high_risk_content = source_has_high_risk_content
_notes_missing_high_risk = notes_missing_high_risk
_high_risk_gap_count = high_risk_gap_count
