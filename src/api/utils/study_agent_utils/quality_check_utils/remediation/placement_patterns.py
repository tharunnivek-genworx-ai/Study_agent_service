"""Shared regex helpers for equation-in-prose detection and remediation."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

SpanConfidence = Literal["high", "low"]

_DISPLAY_MATH_PATTERNS = (
    re.compile(r"\\frac\b"),
    re.compile(r"\\lim\b"),
    re.compile(r"\\int\b"),
    re.compile(r"lim_\{"),
    re.compile(r"\\to\b"),
    re.compile(r"\$\$"),
    re.compile(r"[∫∂Σ]"),
    re.compile(r"→|←|⇒"),
)

_DERIVATIVE_NOTATION_PATTERN = re.compile(r"f'\s*\([^)]*\)")

_EQUALS_PATTERN = re.compile(r"=")

_JS_FUNCTION_PATTERN = re.compile(r"\bfunction\s+(\w+)\s*\(", re.IGNORECASE)
_SINGLE_LETTER_MATH_FUNCTIONS = frozenset("fghxyzuvwtnsrlq")

_NARRATIVE_PREFIX_PATTERN = re.compile(
    r"^(?:for example|for instance|note that|recall that|we have|the|this|a|an)\b",
    re.IGNORECASE,
)

_EQUATION_CORE_PATTERNS = (
    re.compile(r"f\s*'\s*\([^)]*\)\s*=.*", re.IGNORECASE),
    re.compile(r"f\s*\([^)]*\)\s*=.*", re.IGNORECASE),
    re.compile(r"lim[_\{h\s→\\].*", re.IGNORECASE),
    re.compile(r"\\frac\{.*"),
    re.compile(r"\\lim\b.*"),
    re.compile(r"∫.*"),
    re.compile(r"\\int\b.*"),
)


@dataclass(frozen=True)
class EquationSpan:
    start: int
    end: int
    text: str
    confidence: SpanConfidence


def normalize_math(text: str) -> str:
    """Normalize math text for comparison against formula_blocks."""
    normalized = str(text or "").strip().lower()
    normalized = re.sub(r"\s+", "", normalized)
    normalized = normalized.replace("→", "->").replace("←", "<-").replace("⇒", "=>")
    normalized = normalized.replace("−", "-").replace("–", "-")
    return normalized


def _has_display_math(text: str) -> bool:
    return any(pattern.search(text) for pattern in _DISPLAY_MATH_PATTERNS)


def _classify_span(text: str) -> SpanConfidence:
    if _EQUALS_PATTERN.search(text) or _has_display_math(text):
        return "high"
    if _DERIVATIVE_NOTATION_PATTERN.search(text):
        return "low"
    return "high"


def expand_to_equation_clause(text: str, start: int, end: int) -> tuple[int, int]:
    """Expand a match to a natural clause boundary (sentence or if-then)."""
    left = start
    while left > 0 and text[left - 1] not in ".!?\n":
        left -= 1

    prefix_window = text[max(0, left - 120) : start]
    if_match = re.search(r"\bif\b", prefix_window, re.IGNORECASE)
    if if_match:
        left = max(0, left - 120) + if_match.start()

    right = end
    while right < len(text) and text[right] not in ".!?\n":
        right += 1

    return left, right


def _merge_overlapping(text: str, spans: list[EquationSpan]) -> list[EquationSpan]:
    if not spans:
        return []
    ordered = sorted(spans, key=lambda span: (span.start, span.end))
    merged: list[tuple[int, int, SpanConfidence]] = []
    for span in ordered:
        if merged and span.start <= merged[-1][1]:
            prev_start, prev_end, prev_conf = merged[-1]
            new_end = max(prev_end, span.end)
            new_conf: SpanConfidence = (
                "high" if prev_conf == "high" or span.confidence == "high" else "low"
            )
            merged[-1] = (prev_start, new_end, new_conf)
        else:
            merged.append((span.start, span.end, span.confidence))
    return [
        EquationSpan(
            start=start,
            end=end,
            text=text[start:end].strip(),
            confidence=_classify_span(text[start:end]),
        )
        for start, end, _ in merged
        if text[start:end].strip()
    ]


def find_equation_spans(text: str) -> list[EquationSpan]:
    """Return prose spans that look like equations, with confidence tier."""
    if not str(text or "").strip():
        return []

    candidates: list[tuple[int, int]] = []

    for pattern in _DISPLAY_MATH_PATTERNS:
        for match in pattern.finditer(text):
            candidates.append(match.span())

    for match in _EQUALS_PATTERN.finditer(text):
        candidates.append(match.span())

    for match in _DERIVATIVE_NOTATION_PATTERN.finditer(text):
        candidates.append(match.span())

    spans: list[EquationSpan] = []
    seen: set[tuple[int, int]] = set()
    for start, end in candidates:
        clause_start, clause_end = expand_to_equation_clause(text, start, end)
        key = (clause_start, clause_end)
        if key in seen:
            continue
        seen.add(key)
        clause = text[clause_start:clause_end].strip()
        if not clause:
            continue
        confidence = _classify_span(clause)
        spans.append(
            EquationSpan(
                start=clause_start,
                end=clause_end,
                text=clause,
                confidence=confidence,
            )
        )

    return _merge_overlapping(text, spans)


def has_high_confidence_equation_in_content(text: str) -> bool:
    """True when prose contains at least one high-confidence equation span."""
    return any(span.confidence == "high" for span in find_equation_spans(text))


def looks_like_programming_code_in_formula(formula: str) -> bool:
    """True when a formula_block body contains real programming syntax.

    Avoids false positives on calculus prose such as ``the function f(x)``.
    """
    text = str(formula or "")
    if not text.strip():
        return False
    if re.search(r"\bdef\s+\w+\s*\(", text):
        return True
    if re.search(r"\bclass\s+[A-Z]\w*", text):
        return True
    if re.search(r"\bimport\s+\w+", text):
        return True
    for match in _JS_FUNCTION_PATTERN.finditer(text):
        name = match.group(1)
        if len(name) == 1 and name.lower() in _SINGLE_LETTER_MATH_FUNCTIONS:
            continue
        return True
    return False


def is_narrative_equation_clause(text: str) -> bool:
    """True when a span is mostly explanatory prose around a short equation."""
    clause = str(text or "").strip()
    if not clause:
        return False
    if len(clause) > 120:
        return True
    words = re.findall(r"\b\w+\b", clause)
    word_count = len(words)
    if word_count < 6:
        return False
    math_chars = len(re.findall(r"[=^+\-*/()∫∑\\_{}]", clause))
    if word_count >= 8 and math_chars <= max(2, word_count // 2):
        return True
    if _NARRATIVE_PREFIX_PATTERN.search(clause):
        return True
    if re.search(
        r"\bthe\s+(?:function|integral|derivative|limit)\b", clause, re.IGNORECASE
    ):
        return True
    return False


def _trim_equation_tail(core: str) -> str:
    trimmed = str(core or "").strip().rstrip(".,;")
    for pattern in (
        re.compile(r"\s+as\s+x\b.*", re.IGNORECASE),
        re.compile(r"\s+where\b.*", re.IGNORECASE),
    ):
        trimmed = pattern.sub("", trimmed).strip().rstrip(".,;")
    return trimmed


def extract_equation_core(clause: str) -> str | None:
    """Return the tightest equation-like substring from a prose clause."""
    text = str(clause or "").strip()
    if not text:
        return None
    for pattern in _EQUATION_CORE_PATTERNS:
        match = pattern.search(text)
        if match:
            core = _trim_equation_tail(match.group(0))
            if len(core) >= 3:
                return core
    if "=" in text:
        match = re.search(
            r"([A-Za-z0-9_^'()+\-*/\\{}\\s.]+=.+?)(?:\s+as\s+|\s+where\s+|[.,;]|$)",
            text,
            re.IGNORECASE,
        )
        if match:
            core = _trim_equation_tail(match.group(1))
            if len(core) >= 3 and len(core) < len(text):
                return core
    return None


def equation_text_for_formula_block(clause: str) -> str:
    """Choose equation-only text for relocation into formula_blocks."""
    core = extract_equation_core(clause)
    if core and len(core) < len(clause):
        return core
    return clause.strip()
