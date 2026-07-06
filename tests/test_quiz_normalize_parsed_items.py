# tests/test_quiz_normalize_parsed_items.py
"""Unit tests for quiz question parsing normalization."""

from __future__ import annotations

import pytest

from src.api.utils.quiz_utils.generation.question_parsing import (
    empty_to_none,
    normalize_parsed_items,
    normalize_question_markdown,
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
        parsed, _ = normalize_parsed_items([_item()])
        assert parsed[0]["option_c"] == "A reducer"
        assert parsed[0]["option_d"] == "A context"

    def test_rejects_missing_option_c(self):
        with pytest.raises(ValueError, match="option_c"):
            normalize_parsed_items([_item(option_c=None)])

    def test_rejects_missing_option_d(self):
        with pytest.raises(ValueError, match="option_d"):
            normalize_parsed_items([_item(option_d="")])


class TestNormalizeQuestionMarkdown:
    def test_rewrites_inline_fence_after_colon(self):
        raw = "What happens when you call drive?: ```python\nclass Car:\n    pass\n```"
        expected = (
            "What happens when you call drive?\n\n```python\nclass Car:\n    pass\n```"
        )
        assert normalize_question_markdown(raw) == expected

    def test_ensures_closing_fence_on_own_line(self):
        raw = "See below:\n\n```python\nprint(1)```\n"
        assert (
            normalize_question_markdown(raw)
            == "See below:\n\n```python\nprint(1)\n```\n"
        )

    def test_normalizes_question_text_in_parsed_items(self):
        raw_text = "Output?: ```python\nx = 1\n```"
        parsed, _ = normalize_parsed_items([_item(question_text=raw_text)])
        assert parsed[0]["question_text"].startswith("Output?\n\n```python")
