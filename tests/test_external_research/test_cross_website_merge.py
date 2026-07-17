"""Unit tests for cross-website merge (min tokens, retry-on-short)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.api.utils.external_research_utils.cross_website_merge import (
    merge_website_summaries,
)
from src.api.utils.LLM_utils.groq_retry import GroqCallResult


@pytest.mark.asyncio
async def test_merge_retries_when_first_output_below_min_tokens(monkeypatch):
    mock_call = AsyncMock(
        side_effect=[
            GroqCallResult(
                ok=True,
                content='{"ground_truth_reference": "short merge"}',
            ),
            GroqCallResult(
                ok=True,
                content=(
                    '{"ground_truth_reference": "'
                    + " ".join(["union fact"] * 700)
                    + '"}'
                ),
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
        MagicMock(external_research_min_merge_tokens=800),
    )

    result = await merge_website_summaries(
        [
            {
                "url": "https://example.com/a",
                "website_summary": "Site A teaching notes",
            },
            {
                "url": "https://example.com/b",
                "website_summary": "Site B teaching notes",
            },
        ],
        priority_concepts=[],
    )

    assert mock_call.await_count == 2
    retry_payload = mock_call.await_args_list[1].kwargs["messages"][1].content
    assert "too short" in retry_payload.lower()
    assert result["external_research_status"] == "success"
    assert "union fact" in result["ground_truth_reference"]


@pytest.mark.asyncio
async def test_merge_fail_soft_when_still_below_min_after_retry(monkeypatch):
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
        MagicMock(external_research_min_merge_tokens=800),
    )

    result = await merge_website_summaries(
        [{"url": "https://example.com/a", "website_summary": "notes"}],
        priority_concepts=[],
    )

    assert mock_call.await_count == 2
    assert result["external_research_status"] == "fail_soft"
    assert result["external_research_fail_reason"] == "merged_output_below_min_tokens"


def test_default_min_merge_tokens_is_800():
    from src.api.config.external_research_config import ExternalResearchSettings

    settings = ExternalResearchSettings()
    assert settings.external_research_min_merge_tokens == 800
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
