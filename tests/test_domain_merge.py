# tests/test_domain_merge.py
"""Unit tests for domain-aware prompt block merge utilities."""

from __future__ import annotations

from src.api.utils.prompt_utils import (
    VALID_DOMAINS,
    classification_block,
    domains_to_include,
    merge_domain_blocks,
    normalize_domain,
)

_ALL = frozenset({"STEM", "Programming", "Conceptual", "Mixed"})

_SAMPLE_BLOCKS = {
    "STEM": "STEM rules",
    "Programming": "Programming rules",
    "Conceptual": "Conceptual rules",
    "Mixed": "Mixed rules",
}


class TestNormalizeDomain:
    def test_none_returns_empty(self):
        assert normalize_domain(None) == ""

    def test_empty_string_returns_empty(self):
        assert normalize_domain("") == ""

    def test_whitespace_returns_empty(self):
        assert normalize_domain("   ") == ""

    def test_valid_domains_are_preserved(self):
        for domain in VALID_DOMAINS:
            assert normalize_domain(domain) == domain

    def test_valid_domains_strip_whitespace(self):
        assert normalize_domain("  STEM  ") == "STEM"
        assert normalize_domain("\tProgramming\n") == "Programming"

    def test_unknown_values_return_empty(self):
        assert normalize_domain("stem") == ""
        assert normalize_domain("Science") == ""
        assert normalize_domain("STEM+Programming") == ""


class TestDomainsToInclude:
    def test_empty_or_unknown_includes_all(self):
        assert domains_to_include(None) == _ALL
        assert domains_to_include("") == _ALL
        assert domains_to_include("invalid") == _ALL

    def test_mixed_includes_all(self):
        assert domains_to_include("Mixed") == _ALL

    def test_single_domain_includes_only_that_domain(self):
        assert domains_to_include("STEM") == frozenset({"STEM"})
        assert domains_to_include("Programming") == frozenset({"Programming"})
        assert domains_to_include("Conceptual") == frozenset({"Conceptual"})


class TestMergeDomainBlocks:
    def test_empty_domain_includes_all_blocks_in_order(self):
        result = merge_domain_blocks(_SAMPLE_BLOCKS, "")
        assert result == (
            "STEM rules\n\nProgramming rules\n\nConceptual rules\n\nMixed rules"
        )

    def test_mixed_domain_includes_all_blocks(self):
        result = merge_domain_blocks(_SAMPLE_BLOCKS, "Mixed")
        assert result == (
            "STEM rules\n\nProgramming rules\n\nConceptual rules\n\nMixed rules"
        )

    def test_stem_domain_includes_only_stem_block(self):
        result = merge_domain_blocks(_SAMPLE_BLOCKS, "STEM")
        assert result == "STEM rules"
        assert "Programming" not in result

    def test_programming_domain_includes_only_programming_block(self):
        result = merge_domain_blocks(_SAMPLE_BLOCKS, "Programming")
        assert result == "Programming rules"

    def test_conceptual_domain_includes_only_conceptual_block(self):
        result = merge_domain_blocks(_SAMPLE_BLOCKS, "Conceptual")
        assert result == "Conceptual rules"

    def test_header_is_prepended(self):
        result = merge_domain_blocks(
            _SAMPLE_BLOCKS,
            "STEM",
            header="DOMAIN RULES",
        )
        assert result == "DOMAIN RULES\n\nSTEM rules"

    def test_custom_separator(self):
        result = merge_domain_blocks(
            _SAMPLE_BLOCKS,
            "STEM",
            header="HEADER",
            separator="\n---\n",
        )
        assert result == "HEADER\n---\nSTEM rules"

    def test_custom_order(self):
        blocks = {
            "STEM": "stem",
            "Programming": "prog",
            "Conceptual": "concept",
        }
        result = merge_domain_blocks(
            blocks,
            "",
            order=("Conceptual", "Programming", "STEM"),
        )
        assert result == "concept\n\nprog\n\nstem"

    def test_skips_missing_keys(self):
        partial = {"STEM": "STEM only"}
        result = merge_domain_blocks(partial, "")
        assert result == "STEM only"

    def test_empty_header_omitted(self):
        result = merge_domain_blocks(_SAMPLE_BLOCKS, "STEM", header="")
        assert result == "STEM rules"


class TestClassificationBlock:
    def test_unknown_domain_returns_full_text(self):
        full = "STEP 1: classify the topic yourself"
        stub = "Use <domain>; do not reclassify."
        assert (
            classification_block(
                domain="",
                when_unknown=full,
                when_known=stub,
            )
            == full
        )

    def test_none_domain_returns_full_text(self):
        full = "classify"
        stub = "use <domain>"
        assert (
            classification_block(
                domain=None,
                when_unknown=full,
                when_known=stub,
            )
            == full
        )

    def test_known_domain_returns_stub_with_substitution(self):
        full = "classify"
        stub = "`<domain>` is authoritative; do not reclassify."
        assert (
            classification_block(
                domain="STEM",
                when_unknown=full,
                when_known=stub,
            )
            == "`STEM` is authoritative; do not reclassify."
        )

    def test_mixed_domain_returns_stub_not_full_text(self):
        full = "classify"
        stub = "Use <domain>."
        assert (
            classification_block(
                domain="Mixed",
                when_unknown=full,
                when_known=stub,
            )
            == "Use Mixed."
        )
