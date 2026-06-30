"""Domain-specific JSON output schemas for study material generation."""

from __future__ import annotations

from src.api.utils.prompt_utils.domain_merge import normalize_domain

_SECTION_CORE = """\
      "id": "<topic_split id when provided; checklist id otherwise; null for unlisted sections>",
      "heading": "<title>",
      "content": "<prose only — no fenced code blocks, no markdown headings, no equations inside this field>","""

_SUBSECTION_FORMULA = """\
        "heading": "<title>",
        "content": "<prose only — no fenced code blocks, no markdown headings, no equations inside this field>",
        "formula_blocks": [{"notation": "<e.g. LaTeX or plain-text>", "formula": "<the equation, chemical reaction, or derivation step>", "explanation": "<2-3 sentences: what this represents, every variable or term defined, one thing the reader must notice>"}]"""

_SUBSECTION_CODE = """\
        "heading": "<title>",
        "content": "<prose only — no fenced code blocks, no markdown headings, no equations inside this field>",
        "code_blocks": [{"language": "<lang>", "code": "<code>", "explanation": "<2-3 sentences: what this demonstrates, which concept it illustrates, one thing the reader must notice>"}]"""

_SUBSECTION_PROSE = """\
        "heading": "<title>",
        "content": "<prose only — no fenced code blocks, no markdown headings, no equations inside this field>"\
"""

STEM_JSON_OUTPUT_SCHEMA = (
    """\
Output format — return ONLY valid JSON, nothing else:
{
  "sections": [
    {
"""
    + _SECTION_CORE
    + """
      "formula_blocks": [{"notation": "<e.g. LaTeX or plain-text>", "formula": "<the equation, chemical reaction, or derivation step>", "explanation": "<2-3 sentences: what this represents, every variable or term defined, one thing the reader must notice>"}],
      "subsections": [{
"""
    + _SUBSECTION_FORMULA
    + """
      }]
    }
  ]
}
Rules: omit "formula_blocks" and "subsections" entirely when empty. When <topic_split> is present, create exactly one
section per entry with matching id and heading. Do NOT include "code_blocks" anywhere — STEM study material uses
formula_blocks only. Equations, chemical reactions, and mathematical derivations live ONLY inside "formula_blocks" —
never inside "content" and never as executable code. Each formula_block entry is one step or one equation in a chain.
The "explanation" field inside every formula_block entry is mandatory and must not be empty."""
)

PROGRAMMING_JSON_OUTPUT_SCHEMA = (
    """\
Output format — return ONLY valid JSON, nothing else:
{
  "sections": [
    {
"""
    + _SECTION_CORE
    + """
      "code_blocks": [{"language": "<lang>", "code": "<code>", "explanation": "<2-3 sentences: what this demonstrates, which concept it illustrates, one thing the reader must notice>"}],
      "subsections": [{
"""
    + _SUBSECTION_CODE
    + """
      }]
    }
  ]
}
Rules: omit "code_blocks" and "subsections" entirely when empty. When <topic_split> is present, create exactly one
section per entry with matching id and heading. Do NOT include "formula_blocks" anywhere — Programming study material
uses code_blocks only. Source code lives ONLY inside "code_blocks" — never inside "content". Every symbol must be
defined or imported within the same block. The "explanation" field inside every code_block entry is mandatory and
must not be empty."""
)

PROSE_JSON_OUTPUT_SCHEMA = (
    """\
Output format — return ONLY valid JSON, nothing else:
{
  "sections": [
    {
"""
    + _SECTION_CORE
    + """
      "subsections": [{
"""
    + _SUBSECTION_PROSE
    + """
      }]
    }
  ]
}
Rules: omit "subsections" entirely when empty. When <topic_split> is present, create exactly one section per entry
with matching id and heading. Do NOT include "code_blocks" or "formula_blocks" anywhere — Conceptual (prose) study
material expresses definitions, mechanisms, named cases, and causal reasoning in "content" and subsection "content"
only. Never embed equations, reactions, or source code in prose fields."""
)

MIXED_JSON_OUTPUT_SCHEMA = """\
Output format — return ONLY valid JSON, nothing else:
{
  "sections": [
    {
      "id": "<topic_split id when provided; checklist id otherwise; null for unlisted sections>",
      "heading": "<title>",
      "content": "<prose only — no fenced code blocks, no markdown headings, no equations inside this field>",
      "code_blocks": [{"language": "<lang>", "code": "<code>", "explanation": "<2-3 sentences: what this demonstrates, which concept it illustrates, one thing the reader must notice>"}],
      "formula_blocks": [{"notation": "<e.g. LaTeX or plain-text>", "formula": "<the equation, chemical reaction, or derivation step>", "explanation": "<2-3 sentences: what this represents, every variable or term defined, one thing the reader must notice>"}],
      "subsections": [{
        "heading": "<title>",
        "content": "<prose only — no fenced code blocks, no markdown headings, no equations inside this field>",
        "code_blocks": [{"language": "<lang>", "code": "<code>", "explanation": "<2-3 sentences: what this demonstrates, which concept it illustrates, one thing the reader must notice>"}],
        "formula_blocks": [{"notation": "<e.g. LaTeX or plain-text>", "formula": "<the equation, chemical reaction, or derivation step>", "explanation": "<2-3 sentences: what this represents, every variable or term defined, one thing the reader must notice>"}]
      }]
    }
  ]
}
Rules: omit "code_blocks", "formula_blocks", and "subsections" entirely when empty. When <topic_split> is present, create exactly one
section per entry with matching id and heading. Source code lives ONLY inside "code_blocks". Equations, chemical reactions, and
mathematical derivations live ONLY inside "formula_blocks" — never inside "code_blocks" and never as a fenced block inside "content".
A formula_block is not source code: never give it a programming-language "language" value, and never put real programming code
inside one. The "explanation" field inside every code_block and formula_block entry is mandatory and must not be empty.\
"""

# Backward-compatible alias — empty / unknown domain and Mixed use the full schema.
JSON_OUTPUT_SCHEMA = MIXED_JSON_OUTPUT_SCHEMA

_DOMAIN_SCHEMA_MAP: dict[str, str] = {
    "STEM": STEM_JSON_OUTPUT_SCHEMA,
    "Programming": PROGRAMMING_JSON_OUTPUT_SCHEMA,
    "Conceptual": PROSE_JSON_OUTPUT_SCHEMA,
    "Mixed": MIXED_JSON_OUTPUT_SCHEMA,
}


def build_json_output_schema(domain: str | None) -> str:
    """Return the output JSON schema for the given domain classification."""
    normalized = normalize_domain(domain)
    if not normalized or normalized == "Mixed":
        return MIXED_JSON_OUTPUT_SCHEMA
    return _DOMAIN_SCHEMA_MAP[normalized]


def build_section_patch_output_schema(domain: str | None) -> str:
    """Return the section-rework JSON schema for the given domain."""
    normalized = normalize_domain(domain)
    if not normalized or normalized == "Mixed":
        return (
            "Return ONLY valid JSON — no markdown fences, no prose outside the JSON:\n"
            "{\n"
            '  "sections": [\n'
            "    {\n"
            '      "id": "<same id as the failed section — required, do not change>",\n'
            '      "heading": "<title>",\n'
            '      "content": "<prose — no fenced code blocks, no markdown headings, no equations inside this field>",\n'
            '      "code_blocks": [{"language": "<lang>", "code": "<code>", "explanation": "<2-3 sentences>"}],\n'
            '      "formula_blocks": [{"notation": "<e.g. LaTeX or plain-text>", "formula": "<equation or derivation step>", "explanation": "<2-3 sentences>"}],\n'
            '      "subsections": [{"heading": "<title>", "content": "<prose only>", "code_blocks": [...], "formula_blocks": [...]}]\n'
            "    }\n"
            "  ]\n"
            "}\n"
            'Omit "code_blocks", "formula_blocks", and "subsections" when empty. '
            'Preserve each section "id" exactly. Every block "explanation" is mandatory.'
        )
    if normalized == "STEM":
        return (
            "Return ONLY valid JSON — no markdown fences, no prose outside the JSON:\n"
            "{\n"
            '  "sections": [\n'
            "    {\n"
            '      "id": "<same id as the failed section — required, do not change>",\n'
            '      "heading": "<title>",\n'
            '      "content": "<prose only>",\n'
            '      "formula_blocks": [{"notation": "<e.g. LaTeX or plain-text>", "formula": "<equation or derivation step>", "explanation": "<2-3 sentences>"}],\n'
            '      "subsections": [{"heading": "<title>", "content": "<prose only>", "formula_blocks": [...]}]\n'
            "    }\n"
            "  ]\n"
            "}\n"
            'Omit "formula_blocks" and "subsections" when empty. Do NOT include "code_blocks". '
            'Preserve each section "id" exactly. Equations and derivations live only in formula_blocks.'
        )
    if normalized == "Programming":
        return (
            "Return ONLY valid JSON — no markdown fences, no prose outside the JSON:\n"
            "{\n"
            '  "sections": [\n'
            "    {\n"
            '      "id": "<same id as the failed section — required, do not change>",\n'
            '      "heading": "<title>",\n'
            '      "content": "<prose only>",\n'
            '      "code_blocks": [{"language": "<lang>", "code": "<code>", "explanation": "<2-3 sentences>"}],\n'
            '      "subsections": [{"heading": "<title>", "content": "<prose only>", "code_blocks": [...]}]\n'
            "    }\n"
            "  ]\n"
            "}\n"
            'Omit "code_blocks" and "subsections" when empty. Do NOT include "formula_blocks". '
            'Preserve each section "id" exactly. Source code lives only in code_blocks.'
        )
    return (
        "Return ONLY valid JSON — no markdown fences, no prose outside the JSON:\n"
        "{\n"
        '  "sections": [\n'
        "    {\n"
        '      "id": "<same id as the failed section — required, do not change>",\n'
        '      "heading": "<title>",\n'
        '      "content": "<prose only>",\n'
        '      "subsections": [{"heading": "<title>", "content": "<prose only>"}]\n'
        "    }\n"
        "  ]\n"
        "}\n"
        'Omit "subsections" when empty. Do NOT include "code_blocks" or "formula_blocks". '
        'Preserve each section "id" exactly. Express all examples in prose.'
    )
