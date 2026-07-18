"""Unit tests for cross-website merge (adaptive floor, best-available fallback)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.api.utils.external_research_utils.cross_website_merge import (
    effective_merge_min_tokens,
    merge_website_summaries,
)
from src.api.utils.LLM_utils.groq_retry import GroqCallResult


def _merge_settings(
    *,
    min_merge: int = 800,
    absolute: int = 150,
    ratio: float = 0.85,
    best_available: int = 120,
) -> MagicMock:
    return MagicMock(
        external_research_min_merge_tokens=min_merge,
        external_research_min_merge_absolute_tokens=absolute,
        external_research_merge_input_ratio=ratio,
        external_research_min_best_available_tokens=best_available,
    )


@pytest.mark.asyncio
async def test_merge_retries_when_first_output_below_adaptive_min(monkeypatch):
    long_notes = " ".join(["solid teaching fact"] * 400)
    mock_call = AsyncMock(
        side_effect=[
            GroqCallResult(
                ok=True,
                content='{"ground_truth_reference": "short merge"}',
            ),
            GroqCallResult(
                ok=True,
                content='{"ground_truth_reference": "' + long_notes + '"}',
            ),
        ]
    )
    monkeypatch.setattr(
        "src.api.utils.external_research_utils.cross_website_merge.call_groq_with_rotation",
        mock_call,
    )
    monkeypatch.setattr(
        "src.api.utils.external_research_utils.cross_website_merge.llm_settings",
        MagicMock(llm_model="test-model"),
    )
    monkeypatch.setattr(
        "src.api.utils.external_research_utils.cross_website_merge.external_research_settings",
        _merge_settings(),
    )

    result = await merge_website_summaries(
        [
            {
                "url": "https://example.com/a",
                "website_summary": long_notes,
            },
            {
                "url": "https://example.com/b",
                "website_summary": " ".join(["extra fact"] * 100),
            },
        ],
        priority_concepts=[],
    )

    assert mock_call.await_count == 2
    retry_payload = mock_call.await_args_list[1].kwargs["messages"][1].content
    assert "too short" in retry_payload.lower()
    assert result["external_research_status"] == "success"
    assert "solid teaching fact" in result["ground_truth_reference"]


@pytest.mark.asyncio
async def test_merge_uses_best_available_when_still_below_min(monkeypatch):
    strong = " ".join(["calvin cycle stage"] * 80)  # ~312 rough tokens
    thin = "No useful details about the checklist concepts."
    mock_call = AsyncMock(
        return_value=GroqCallResult(
            ok=True,
            content='{"ground_truth_reference": "still too thin"}',
        )
    )
    monkeypatch.setattr(
        "src.api.utils.external_research_utils.cross_website_merge.call_groq_with_rotation",
        mock_call,
    )
    monkeypatch.setattr(
        "src.api.utils.external_research_utils.cross_website_merge.llm_settings",
        MagicMock(llm_model="test-model"),
    )
    # Force a high floor so short merge fails; best-available should still win.
    monkeypatch.setattr(
        "src.api.utils.external_research_utils.cross_website_merge.external_research_settings",
        _merge_settings(min_merge=800, absolute=800, ratio=1.0, best_available=120),
    )

    result = await merge_website_summaries(
        [
            {
                "url": "https://bio.libretexts.org/calvin",
                "website_summary": strong,
            },
            {
                "url": "https://example.com/thin",
                "website_summary": thin,
            },
        ],
        priority_concepts=[],
    )

    assert mock_call.await_count == 2
    assert result["external_research_status"] == "success"
    assert result["ground_truth_reference"] == strong
    assert result["external_source_urls"] == ["https://bio.libretexts.org/calvin"]


@pytest.mark.asyncio
async def test_merge_fail_soft_when_no_usable_best_available(monkeypatch):
    mock_call = AsyncMock(
        return_value=GroqCallResult(
            ok=True,
            content='{"ground_truth_reference": "still too thin"}',
        )
    )
    monkeypatch.setattr(
        "src.api.utils.external_research_utils.cross_website_merge.call_groq_with_rotation",
        mock_call,
    )
    monkeypatch.setattr(
        "src.api.utils.external_research_utils.cross_website_merge.llm_settings",
        MagicMock(llm_model="test-model"),
    )
    monkeypatch.setattr(
        "src.api.utils.external_research_utils.cross_website_merge.external_research_settings",
        _merge_settings(min_merge=800, absolute=800, ratio=1.0, best_available=120),
    )

    result = await merge_website_summaries(
        [{"url": "https://example.com/a", "website_summary": "tiny notes"}],
        priority_concepts=[],
    )

    assert mock_call.await_count == 2
    assert result["external_research_status"] == "fail_soft"
    assert result["external_research_fail_reason"] == "merged_output_below_min_tokens"
    assert result["ground_truth_reference"] is None
    assert result["external_source_urls"] == []


@pytest.mark.asyncio
async def test_merge_llm_failure_falls_back_to_best_available(monkeypatch):
    strong = " ".join(["equation and named law"] * 60)
    mock_call = AsyncMock(
        return_value=GroqCallResult(ok=False, content=None, error_type="timeout")
    )
    monkeypatch.setattr(
        "src.api.utils.external_research_utils.cross_website_merge.call_groq_with_rotation",
        mock_call,
    )
    monkeypatch.setattr(
        "src.api.utils.external_research_utils.cross_website_merge.llm_settings",
        MagicMock(llm_model="test-model"),
    )
    monkeypatch.setattr(
        "src.api.utils.external_research_utils.cross_website_merge.external_research_settings",
        _merge_settings(),
    )

    result = await merge_website_summaries(
        [{"url": "https://example.edu/notes", "website_summary": strong}],
        priority_concepts=[],
    )

    assert result["external_research_status"] == "success"
    assert result["ground_truth_reference"] == strong
    assert result["external_source_urls"] == ["https://example.edu/notes"]


def test_effective_merge_min_tokens_scales_with_short_sources(monkeypatch):
    monkeypatch.setattr(
        "src.api.utils.external_research_utils.cross_website_merge.external_research_settings",
        _merge_settings(min_merge=800, absolute=150, ratio=0.85),
    )
    # ~388 tokens of source notes → floor ~329, not 800
    short_a = " ".join(["word"] * 200)  # 260
    short_b = " ".join(["word"] * 80)  # 104
    floor = effective_merge_min_tokens([short_a, short_b])
    assert floor < 800
    assert floor >= 150


def test_effective_merge_min_tokens_caps_when_sources_are_rich(monkeypatch):
    monkeypatch.setattr(
        "src.api.utils.external_research_utils.cross_website_merge.external_research_settings",
        _merge_settings(min_merge=800, absolute=150, ratio=0.85),
    )
    rich = " ".join(["fact"] * 2000)
    assert effective_merge_min_tokens([rich]) == 800


def test_default_merge_settings():
    from src.api.config.external_research_config import ExternalResearchSettings

    settings = ExternalResearchSettings()
    assert settings.external_research_min_merge_tokens == 800
    assert settings.external_research_min_merge_absolute_tokens == 150
    assert settings.external_research_merge_input_ratio == 0.85
    assert settings.external_research_min_best_available_tokens == 120
    assert settings.external_research_min_distill_note_tokens == 120
    assert settings.external_research_min_distill_keep_ratio == 0.08


def test_merge_prompt_union_dedupe_not_resummarize():
    from src.api.control.study_agent.prompts.external_research import (
        CROSS_WEBSITE_MERGE_PROMPT,
    )

    lower = CROSS_WEBSITE_MERGE_PROMPT.lower()
    assert "union" in lower
    assert "dedupe" in lower or "dedupe" in CROSS_WEBSITE_MERGE_PROMPT
    assert "overview" in lower
    assert "widget law" in lower
    assert "wave" not in lower
    assert "react hooks" not in lower
