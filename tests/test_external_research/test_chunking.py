"""Unit tests for external-research conditional chunking (§8)."""

from __future__ import annotations

from src.api.utils.external_research_utils.chunking import (
    chunk_cleaned_pages,
    split_into_chunks,
)
from src.api.utils.external_research_utils.tokens import rough_token_count


def _words(n: int, prefix: str = "word") -> str:
    return " ".join(f"{prefix}{i}" for i in range(n))


def test_single_newline_long_page_produces_multiple_chunks():
    """Wave-like pages use only ``\\n``; must still chunk when over threshold."""
    # ~1.3 tokens/word → 2500 words ≈ 3250 tokens (above default-like 300)
    lines = [_words(50, prefix=f"L{i}_") for i in range(50)]  # 2500 words
    text = "\n".join(lines)
    assert "\n\n" not in text
    assert rough_token_count(text) > 300

    chunks = split_into_chunks(text, target_tokens=300)
    assert len(chunks) > 1
    for chunk in chunks:
        assert rough_token_count(chunk) <= 300


def test_double_newline_page_packs_paragraphs():
    paragraphs = [_words(80, prefix=f"P{i}_") for i in range(10)]
    text = "\n\n".join(paragraphs)
    assert rough_token_count(text) > 200

    chunks = split_into_chunks(text, target_tokens=200)
    assert len(chunks) > 1
    for chunk in chunks:
        assert rough_token_count(chunk) <= 200


def test_page_under_threshold_one_chunk_was_chunked_false(monkeypatch):
    monkeypatch.setattr(
        "src.api.utils.external_research_utils.chunking.external_research_settings",
        type("S", (), {"external_research_chunk_token_threshold": 3000})(),
    )
    text = _words(100)  # ~130 tokens
    result = chunk_cleaned_pages(
        [{"url": "https://example.com/a", "cleaned_text": text}]
    )
    assert len(result) == 1
    assert result[0]["chunks"] == [text]
    assert result[0]["was_chunked"] is False


def test_oversized_paragraph_no_newlines_hard_splits():
    """A single mega-paragraph with no newlines must still hard-split."""
    text = _words(1000)  # ~1300 tokens, no newlines at all
    assert "\n" not in text
    chunks = split_into_chunks(text, target_tokens=200)
    assert len(chunks) > 1
    for chunk in chunks:
        assert rough_token_count(chunk) <= 200


def test_was_chunked_true_only_when_multiple_chunks(monkeypatch):
    monkeypatch.setattr(
        "src.api.utils.external_research_utils.chunking.external_research_settings",
        type("S", (), {"external_research_chunk_token_threshold": 200})(),
    )
    text = "\n".join(_words(40, prefix=f"row{i}_") for i in range(20))
    assert rough_token_count(text) > 200

    result = chunk_cleaned_pages(
        [{"url": "https://example.com/long", "cleaned_text": text}]
    )
    assert len(result[0]["chunks"]) > 1
    assert result[0]["was_chunked"] is True


def test_wave_like_7k_token_fixture_chunks():
    """~7k-token single-``\\n`` page (STEM/EBSCO shape) → multiple chunks at 3000."""
    # 5400 words * 1.3 ≈ 7020 tokens
    lines = [_words(60, prefix=f"W{i}_") for i in range(90)]
    text = "\n".join(lines)
    assert "\n\n" not in text
    assert rough_token_count(text) > 3000

    chunks = split_into_chunks(text, target_tokens=3000)
    assert len(chunks) >= 2
    for chunk in chunks:
        assert rough_token_count(chunk) <= 3000


def test_crlf_normalized_before_chunking():
    paragraphs = [_words(100, prefix=f"C{i}_") for i in range(6)]
    text = "\r\n\r\n".join(paragraphs)
    chunks = split_into_chunks(text, target_tokens=200)
    assert len(chunks) > 1
    for chunk in chunks:
        assert "\r" not in chunk
        assert rough_token_count(chunk) <= 200


def test_hard_split_by_sentences_when_no_paragraph_breaks():
    sentences = [f"{_words(40, prefix=f'S{i}_')}. " for i in range(15)]
    text = "".join(sentences).strip()
    assert "\n" not in text
    chunks = split_into_chunks(text, target_tokens=150)
    assert len(chunks) > 1
    for chunk in chunks:
        assert rough_token_count(chunk) <= 150
