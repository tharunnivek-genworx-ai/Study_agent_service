# tests/test_output_schemas.py
"""Unit tests for domain-specific study material output schemas."""

from __future__ import annotations

from src.api.control.study_agent.prompts.generation.output_schemas import (
    MIXED_JSON_OUTPUT_SCHEMA,
    PROGRAMMING_JSON_OUTPUT_SCHEMA,
    PROSE_JSON_OUTPUT_SCHEMA,
    STEM_JSON_OUTPUT_SCHEMA,
    build_json_output_schema,
)


class TestOutputSchemas:
    def test_empty_domain_uses_mixed_schema(self):
        assert build_json_output_schema("") == MIXED_JSON_OUTPUT_SCHEMA
        assert build_json_output_schema(None) == MIXED_JSON_OUTPUT_SCHEMA

    def test_mixed_domain_uses_full_schema(self):
        assert build_json_output_schema("Mixed") == MIXED_JSON_OUTPUT_SCHEMA
        assert "code_blocks" in build_json_output_schema("Mixed")
        assert "formula_blocks" in build_json_output_schema("Mixed")

    def test_stem_schema_excludes_code_blocks(self):
        schema = build_json_output_schema("STEM")
        assert schema == STEM_JSON_OUTPUT_SCHEMA
        assert '"formula_blocks":' in schema
        assert '"code_blocks":' not in schema

    def test_programming_schema_excludes_formula_blocks(self):
        schema = build_json_output_schema("Programming")
        assert schema == PROGRAMMING_JSON_OUTPUT_SCHEMA
        assert '"code_blocks":' in schema
        assert '"formula_blocks":' not in schema

    def test_conceptual_schema_is_prose_only(self):
        schema = build_json_output_schema("Conceptual")
        assert schema == PROSE_JSON_OUTPUT_SCHEMA
        assert '"code_blocks":' not in schema
        assert '"formula_blocks":' not in schema
