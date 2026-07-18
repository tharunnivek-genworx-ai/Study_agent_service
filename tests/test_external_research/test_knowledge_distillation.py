"""Unit tests for knowledge distillation (continues_next_chunk, retention retry)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from src.api.utils.external_research_utils.distill_retention import (
    high_risk_gap_count,
    notes_missing_high_risk,
    source_has_high_risk_content,
)
from src.api.utils.external_research_utils.knowledge_distillation import (
    build_knowledge_user_payload,
    distill_chunked_pages,
)
from src.api.utils.LLM_utils.groq_retry import GroqCallResult

_CODE_CHUNK = """WidgetAPI overview.

```python
def connect(timeout_ms: int) -> None:
    client = WidgetClient(timeout_ms)
    client.open()
```

Also: WidgetAPI.connect(timeout_ms) raises TimeoutError.
"""

_EQ_CHUNK = """Widget Law (19XX): the force relation is

$$F = k \\cdot q$$

Derivation step: isolate q on both sides.
"""


def _settings_mock(
    *,
    min_tokens: int = 1,
    keep_ratio: float = 0.0,
    content_retention_retry: bool = True,
) -> MagicMock:
    return MagicMock(
        external_research_min_distill_note_tokens=min_tokens,
        external_research_min_distill_keep_ratio=keep_ratio,
        external_research_distill_content_retention_retry=content_retention_retry,
    )


def test_build_payload_includes_continuation_context():
    payload = build_knowledge_user_payload(
        "chunk body",
        ["concept-a"],
        previous_chunk_ended_mid_thought=True,
    )
    assert "PREVIOUS_CHUNK_ENDED_MID_THOUGHT: true" in payload
    assert "do not invent the missing half" in payload
    assert "SOURCE_CHUNK:\nchunk body" in payload


def test_build_payload_includes_retention_retry_reminder():
    payload = build_knowledge_user_payload(
        "chunk body",
        [],
        retention_retry=True,
    )
    assert "previous draft was too short" in payload.lower()
    assert "verbatim code" in payload.lower()


def test_build_payload_includes_content_gap_retry_reminder():
    payload = build_knowledge_user_payload(
        "chunk body",
        [],
        retention_retry=True,
        content_gap_retry=True,
    )
    assert "omitted verbatim code" in payload.lower()
    assert "syntax-only" in payload.lower()
    assert "previous draft was too short" not in payload.lower()


def test_source_has_high_risk_fenced_code():
    assert source_has_high_risk_content(_CODE_CHUNK) is True
    assert source_has_high_risk_content("plain prose about widgets only.") is False


def test_source_has_high_risk_equation():
    assert source_has_high_risk_content(_EQ_CHUNK) is True


def test_notes_missing_high_risk_when_code_dropped():
    prose_only = (
        "WidgetAPI lets you connect with a timeout. It may raise TimeoutError. " * 20
    )
    assert notes_missing_high_risk(_CODE_CHUNK, prose_only) is True


def test_notes_not_missing_high_risk_when_code_kept():
    notes = (
        "- API overview\n"
        "```python\n"
        "def connect(timeout_ms: int) -> None:\n"
        "    client = WidgetClient(timeout_ms)\n"
        "    client.open()\n"
        "```\n"
        "- raises TimeoutError"
    )
    assert notes_missing_high_risk(_CODE_CHUNK, notes) is False
    assert high_risk_gap_count(_CODE_CHUNK, notes) == 0


def test_high_risk_gap_count_decreases_when_code_restored():
    missing = "WidgetAPI overview and TimeoutError only."
    restored = (
        "```python\n"
        "def connect(timeout_ms: int) -> None:\n"
        "    client = WidgetClient(timeout_ms)\n"
        "    client.open()\n"
        "```"
    )
    assert high_risk_gap_count(_CODE_CHUNK, missing) > high_risk_gap_count(
        _CODE_CHUNK, restored
    )


@pytest.mark.asyncio
async def test_continues_next_chunk_prepends_context_to_next_chunk(monkeypatch):
    calls: list[str] = []

    async def fake_call(*, messages, **kwargs):
        user_content = messages[1].content
        calls.append(user_content)
        if len(calls) == 1:
            return GroqCallResult(
                ok=True,
                content='{"knowledge_notes": "part one of code block", "continues_next_chunk": true}',
            )
        return GroqCallResult(
            ok=True,
            content='{"knowledge_notes": "part two completes block", "continues_next_chunk": false}',
        )

    monkeypatch.setattr(
        "src.api.utils.external_research_utils.knowledge_distillation.call_groq_with_rotation",
        fake_call,
    )
    monkeypatch.setattr(
        "src.api.utils.external_research_utils.knowledge_distillation.llm_settings",
        MagicMock(llm_model="test-model"),
    )
    monkeypatch.setattr(
        "src.api.utils.external_research_utils.knowledge_distillation.external_research_settings",
        _settings_mock(),
    )

    distilled, _ = await distill_chunked_pages(
        [
            {
                "url": "https://example.com/page",
                "chunks": ["chunk A text", "chunk B text"],
                "was_chunked": True,
            }
        ],
        domain="Programming",
        priority_concepts=[],
    )

    assert len(calls) == 2
    assert "PREVIOUS_CHUNK_ENDED_MID_THOUGHT" not in calls[0]
    assert "PREVIOUS_CHUNK_ENDED_MID_THOUGHT: true" in calls[1]
    assert distilled == [
        {
            "url": "https://example.com/page",
            "notes": ["part one of code block", "part two completes block"],
            "was_chunked": True,
        }
    ]


@pytest.mark.asyncio
async def test_retention_retry_keeps_longer_of_two_attempts(monkeypatch):
    call_count = 0

    async def fake_call(*, messages, **kwargs):
        nonlocal call_count
        call_count += 1
        user_content = messages[1].content
        if "previous draft was too short" in user_content.lower():
            return GroqCallResult(
                ok=True,
                content=(
                    '{"knowledge_notes": "'
                    + " ".join(["dense fact"] * 80)
                    + '", "continues_next_chunk": false}'
                ),
            )
        return GroqCallResult(
            ok=True,
            content='{"knowledge_notes": "too brief", "continues_next_chunk": false}',
        )

    monkeypatch.setattr(
        "src.api.utils.external_research_utils.knowledge_distillation.call_groq_with_rotation",
        fake_call,
    )
    monkeypatch.setattr(
        "src.api.utils.external_research_utils.knowledge_distillation.llm_settings",
        MagicMock(llm_model="test-model"),
    )
    monkeypatch.setattr(
        "src.api.utils.external_research_utils.knowledge_distillation.external_research_settings",
        _settings_mock(min_tokens=120, keep_ratio=0.08),
    )

    long_chunk = " ".join(["source word"] * 500)
    distilled, _ = await distill_chunked_pages(
        [
            {
                "url": "https://example.com/long",
                "chunks": [long_chunk],
                "was_chunked": False,
            }
        ],
        domain="STEM",
        priority_concepts=[],
    )

    assert call_count == 2
    assert len(distilled) == 1
    assert "dense fact" in distilled[0]["notes"][0]


@pytest.mark.asyncio
async def test_long_prose_missing_code_triggers_content_retention_retry(monkeypatch):
    """Length-ok notes that drop fenced code still trigger a content-gap retry."""
    calls: list[str] = []
    long_prose = " ".join(
        ["WidgetAPI connects with timeouts and may raise TimeoutError."] * 40
    )
    restored = (
        long_prose
        + "\n```python\ndef connect(timeout_ms: int) -> None:\n"
        + "    client = WidgetClient(timeout_ms)\n    client.open()\n```"
    )

    async def fake_call(*, messages, **kwargs):
        user_content = messages[1].content
        calls.append(user_content)
        if "omitted verbatim code" in user_content.lower():
            return GroqCallResult(
                ok=True,
                content=(
                    '{"knowledge_notes": '
                    + __import__("json").dumps(restored)
                    + ', "continues_next_chunk": false}'
                ),
            )
        return GroqCallResult(
            ok=True,
            content=(
                '{"knowledge_notes": '
                + __import__("json").dumps(long_prose)
                + ', "continues_next_chunk": false}'
            ),
        )

    monkeypatch.setattr(
        "src.api.utils.external_research_utils.knowledge_distillation.call_groq_with_rotation",
        fake_call,
    )
    monkeypatch.setattr(
        "src.api.utils.external_research_utils.knowledge_distillation.llm_settings",
        MagicMock(llm_model="test-model"),
    )
    monkeypatch.setattr(
        "src.api.utils.external_research_utils.knowledge_distillation.external_research_settings",
        _settings_mock(min_tokens=1, keep_ratio=0.0),
    )

    distilled, _ = await distill_chunked_pages(
        [
            {
                "url": "https://example.com/code",
                "chunks": [_CODE_CHUNK],
                "was_chunked": False,
            }
        ],
        domain="Programming",
        priority_concepts=[],
    )

    assert len(calls) == 2
    assert "omitted verbatim code" in calls[1].lower()
    assert "def connect" in distilled[0]["notes"][0]


@pytest.mark.asyncio
async def test_content_retry_prefers_gap_reducing_attempt_even_if_shorter(
    monkeypatch,
):
    """When retry restores code but is shorter, prefer the gap-reducing attempt."""
    long_prose = " ".join(["overview sentence about WidgetAPI timeouts."] * 50)
    short_with_code = (
        "```python\ndef connect(timeout_ms: int) -> None:\n"
        "    client = WidgetClient(timeout_ms)\n    client.open()\n```"
    )

    async def fake_call(*, messages, **kwargs):
        user_content = messages[1].content
        if "omitted verbatim code" in user_content.lower():
            return GroqCallResult(
                ok=True,
                content=(
                    '{"knowledge_notes": '
                    + __import__("json").dumps(short_with_code)
                    + ', "continues_next_chunk": false}'
                ),
            )
        return GroqCallResult(
            ok=True,
            content=(
                '{"knowledge_notes": '
                + __import__("json").dumps(long_prose)
                + ', "continues_next_chunk": false}'
            ),
        )

    monkeypatch.setattr(
        "src.api.utils.external_research_utils.knowledge_distillation.call_groq_with_rotation",
        fake_call,
    )
    monkeypatch.setattr(
        "src.api.utils.external_research_utils.knowledge_distillation.llm_settings",
        MagicMock(llm_model="test-model"),
    )
    monkeypatch.setattr(
        "src.api.utils.external_research_utils.knowledge_distillation.external_research_settings",
        _settings_mock(min_tokens=1, keep_ratio=0.0),
    )

    distilled, _ = await distill_chunked_pages(
        [
            {
                "url": "https://example.com/prefer-code",
                "chunks": [_CODE_CHUNK],
                "was_chunked": False,
            }
        ],
        domain="Programming",
        priority_concepts=[],
    )

    assert "def connect" in distilled[0]["notes"][0]
    assert "overview sentence" not in distilled[0]["notes"][0]


@pytest.mark.asyncio
async def test_no_content_retry_when_notes_already_contain_code(monkeypatch):
    call_count = 0
    notes_with_code = (
        "Teaching prep:\n"
        "```python\ndef connect(timeout_ms: int) -> None:\n"
        "    client = WidgetClient(timeout_ms)\n    client.open()\n```\n"
        "Raises TimeoutError."
    )

    async def fake_call(*, messages, **kwargs):
        nonlocal call_count
        call_count += 1
        return GroqCallResult(
            ok=True,
            content=(
                '{"knowledge_notes": '
                + __import__("json").dumps(notes_with_code)
                + ', "continues_next_chunk": false}'
            ),
        )

    monkeypatch.setattr(
        "src.api.utils.external_research_utils.knowledge_distillation.call_groq_with_rotation",
        fake_call,
    )
    monkeypatch.setattr(
        "src.api.utils.external_research_utils.knowledge_distillation.llm_settings",
        MagicMock(llm_model="test-model"),
    )
    monkeypatch.setattr(
        "src.api.utils.external_research_utils.knowledge_distillation.external_research_settings",
        _settings_mock(min_tokens=1, keep_ratio=0.0),
    )

    distilled, _ = await distill_chunked_pages(
        [
            {
                "url": "https://example.com/kept-code",
                "chunks": [_CODE_CHUNK],
                "was_chunked": False,
            }
        ],
        domain="Programming",
        priority_concepts=[],
    )

    assert call_count == 1
    assert distilled[0]["notes"][0] == notes_with_code


@pytest.mark.asyncio
async def test_content_retention_retry_disabled_by_flag(monkeypatch):
    call_count = 0
    long_prose = " ".join(
        ["WidgetAPI connects with timeouts and may raise TimeoutError."] * 40
    )

    async def fake_call(*, messages, **kwargs):
        nonlocal call_count
        call_count += 1
        return GroqCallResult(
            ok=True,
            content=(
                '{"knowledge_notes": '
                + __import__("json").dumps(long_prose)
                + ', "continues_next_chunk": false}'
            ),
        )

    monkeypatch.setattr(
        "src.api.utils.external_research_utils.knowledge_distillation.call_groq_with_rotation",
        fake_call,
    )
    monkeypatch.setattr(
        "src.api.utils.external_research_utils.knowledge_distillation.llm_settings",
        MagicMock(llm_model="test-model"),
    )
    monkeypatch.setattr(
        "src.api.utils.external_research_utils.knowledge_distillation.external_research_settings",
        _settings_mock(min_tokens=1, keep_ratio=0.0, content_retention_retry=False),
    )

    distilled, _ = await distill_chunked_pages(
        [
            {
                "url": "https://example.com/flag-off",
                "chunks": [_CODE_CHUNK],
                "was_chunked": False,
            }
        ],
        domain="Programming",
        priority_concepts=[],
    )

    assert call_count == 1
    assert distilled[0]["notes"][0] == long_prose


def test_stem_prompt_teaching_prep_tone_no_mvp_topics():
    from src.api.control.study_agent.prompts.external_research import (
        STEM_DISTILLATION_PROMPT,
    )

    lower = STEM_DISTILLATION_PROMPT.lower()
    assert "teaching-prep" in lower or "teaching prep" in lower
    assert "densify pass" in lower
    assert "widget law" in lower
    assert "wave" not in lower
    assert "react hooks" not in lower
    assert "usestate" not in lower


def test_stem_preserve_hardens_years_experiments_equations_softens_numerics():
    from src.api.control.study_agent.prompts.external_research.knowledge_distillation_prompt_stem import (
        _STEM_PRESERVE,
    )

    lower = _STEM_PRESERVE.lower()
    assert "every date and year" in lower
    assert "named" in lower and "experiment" in lower
    assert "equation" in lower
    assert "davisson" in lower or "compton" in lower or "year or stated form" in lower
    # Soften all-numerics pressure: prefer representative, not every table/drill.
    assert "representative" in lower
    assert "do not retain every numeric" in lower or "every numeric example" in lower
    assert "parameter table" in lower
    # Must not still mandate retaining every worked numeric / full tables.
    assert "worked numeric examples including the specific numbers used" not in lower
    assert "tables of values or parameters" not in lower


def test_programming_prompt_keeps_full_examples_rule():
    from src.api.control.study_agent.prompts.external_research import (
        PROGRAMMING_DISTILLATION_PROMPT,
    )

    lower = PROGRAMMING_DISTILLATION_PROMPT.lower()
    assert "1–2 full" in PROGRAMMING_DISTILLATION_PROMPT or "1-2 full" in lower
    assert "syntax-only" in lower
    assert "verbatim" in lower


def test_conceptual_and_mixed_preserve_incidental_code_equations():
    from src.api.control.study_agent.prompts.external_research import (
        CONCEPTUAL_DISTILLATION_PROMPT,
        MIXED_DISTILLATION_PROMPT,
    )

    conceptual = CONCEPTUAL_DISTILLATION_PROMPT.lower()
    mixed = " ".join(MIXED_DISTILLATION_PROMPT.lower().split())
    assert "verbatim" in conceptual
    assert "equation" in conceptual
    assert "code" in conceptual
    assert "dual-precision" in mixed
    assert "never collapse an equation into prose" in mixed
