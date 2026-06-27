# tests/test_quiz_normalize_parsed_items.py
"""Unit tests for quiz question parsing normalization."""

from __future__ import annotations

import pytest

from src.api.utils.quiz_utils.generation.question_parsing import (
    empty_to_none,
    normalize_parsed_items,
)


def _item(**overrides) -> dict:
    base = {
        "question_text": "What is useState?",
        "option_a": "A hook",
        "option_b": "A component",
        "option_c": "A reducer",
        "option_d": "A context",
        "correct_option": "A",
        "explanation": "useState is a React hook.",
    }
    base.update(overrides)
    return base


class TestEmptyToNone:
    def test_preserves_non_empty_option_values(self):
        assert empty_to_none("Reducer") == "Reducer"
        assert empty_to_none("Context API") == "Context API"

    def test_empty_string_becomes_none(self):
        assert empty_to_none("") is None
        assert empty_to_none("   ") is None


class TestNormalizeParsedItems:
    def test_preserves_option_c_and_d(self):
        parsed, _ = normalize_parsed_items([_item()], {})
        assert parsed[0]["option_c"] == "A reducer"
        assert parsed[0]["option_d"] == "A context"

    def test_rejects_missing_option_c(self):
        with pytest.raises(ValueError, match="option_c"):
            normalize_parsed_items([_item(option_c=None)], {})

    def test_rejects_missing_option_d(self):
        with pytest.raises(ValueError, match="option_d"):
            normalize_parsed_items([_item(option_d="")], {})
