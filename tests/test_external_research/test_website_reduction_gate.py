"""Unit tests for website-reduction gate (len(notes) > 1)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.api.utils.external_research_utils.website_reduction import (
    reduce_distilled_pages,
)
from src.api.utils.LLM_utils.groq_retry import GroqCallResult


@pytest.mark.asyncio
async def test_single_note_skips_llm_even_when_was_chunked_true(monkeypatch):
    """STEM-style false flag: was_chunked=True but only one note — no LLM."""
    mock_call = AsyncMock()
    monkeypatch.setattr(
        "src.api.utils.external_research_utils.website_reduction.call_groq_with_rotation",
        mock_call,
    )
    monkeypatch.setattr(
        "src.api.utils.external_research_utils.website_reduction.llm_settings",
        MagicMock(llm_model="test-model"),
    )

    note = (
        "Widget Law: F = k·q (19XX). Derivation keeps the constant with units. "
        "Named experiment: Widget Trial."
    )
    result = await reduce_distilled_pages(
        [
            {
                "url": "https://example.com/stem",
                "notes": [note],
                "was_chunked": True,
            }
        ]
    )

    mock_call.assert_not_awaited()
    assert result == [{"url": "https://example.com/stem", "website_summary": note}]


@pytest.mark.asyncio
async def test_single_note_unchunked_passes_through(monkeypatch):
    mock_call = AsyncMock()
    monkeypatch.setattr(
        "src.api.utils.external_research_utils.website_reduction.call_groq_with_rotation",
        mock_call,
    )
    monkeypatch.setattr(
        "src.api.utils.external_research_utils.website_reduction.llm_settings",
        MagicMock(llm_model="test-model"),
    )

    note = "Dense teaching-prep note with a date 20XX and equation E = mc^2."
    result = await reduce_distilled_pages(
        [
            {
                "url": "https://example.com/wiki",
                "notes": [note],
                "was_chunked": False,
            }
        ]
    )

    mock_call.assert_not_awaited()
    assert result == [{"url": "https://example.com/wiki", "website_summary": note}]


@pytest.mark.asyncio
async def test_multiple_notes_calls_llm(monkeypatch):
    mock_call = AsyncMock(
        return_value=GroqCallResult(
            ok=True,
            content='{"website_summary": "merged teaching-prep notes"}',
        )
    )
    monkeypatch.setattr(
        "src.api.utils.external_research_utils.website_reduction.call_groq_with_rotation",
        mock_call,
    )
    monkeypatch.setattr(
        "src.api.utils.external_research_utils.website_reduction.llm_settings",
        MagicMock(llm_model="test-model"),
    )

    result = await reduce_distilled_pages(
        [
            {
                "url": "https://example.com/long",
                "notes": ["note chunk A with code", "note chunk B with equation"],
                "was_chunked": True,
            }
        ]
    )

    mock_call.assert_awaited_once()
    assert result == [
        {
            "url": "https://example.com/long",
            "website_summary": "merged teaching-prep notes",
        }
    ]


@pytest.mark.asyncio
async def test_empty_notes_skipped(monkeypatch):
    mock_call = AsyncMock()
    monkeypatch.setattr(
        "src.api.utils.external_research_utils.website_reduction.call_groq_with_rotation",
        mock_call,
    )
    monkeypatch.setattr(
        "src.api.utils.external_research_utils.website_reduction.llm_settings",
        MagicMock(llm_model="test-model"),
    )

    result = await reduce_distilled_pages(
        [{"url": "https://example.com/empty", "notes": [], "was_chunked": False}]
    )

    mock_call.assert_not_awaited()
    assert result == []


def test_reduction_prompt_forbids_overview_rewrite():
    from src.api.control.study_agent.prompts.external_research import (
        WEBSITE_REDUCTION_PROMPT,
    )

    lower = WEBSITE_REDUCTION_PROMPT.lower()
    assert "teaching-prep" in lower or "teaching prep" in lower
    assert "overview" in lower
    assert "unique" in lower
    assert "single note" in lower or "unchanged" in lower
