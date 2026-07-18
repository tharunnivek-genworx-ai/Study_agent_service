"""Knowledge distillation via call_groq_with_rotation (design §9)."""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from src.api.config import external_research_settings, llm_settings
from src.api.control.study_agent.prompts.external_research import (
    DISTILLATION_PROMPTS_BY_DOMAIN,
    MIXED_DISTILLATION_PROMPT,
)
from src.api.utils.external_research_utils.abort import (
    ShouldContinueAsync,
    abort_if_should_stop,
)
from src.api.utils.external_research_utils.distill_retention import (
    high_risk_gap_count,
    notes_missing_high_risk,
    source_has_high_risk_content,
)
from src.api.utils.external_research_utils.json_parse import parse_json_object
from src.api.utils.external_research_utils.tokens import rough_token_count
from src.api.utils.LLM_utils.groq_retry import GroqCallResult, call_groq_with_rotation

logger = logging.getLogger(__name__)

_RETENTION_RETRY_REMINDER = (
    "\n\nREMINDER: Your previous draft was too short. Restore missing verbatim "
    "code, equations, dates, and named entities from SOURCE_CHUNK. Denser "
    "bullets and short paragraphs are OK."
)

_CONTENT_GAP_RETRY_REMINDER = (
    "\n\nREMINDER: Your previous draft omitted verbatim code and/or equations "
    "from SOURCE_CHUNK. Restore omitted code blocks and equations VERBATIM — "
    "do not replace them with syntax-only catalogs or prose summaries."
)


def extract_priority_concept_names(
    must_cover_checklist: list[dict[str, Any]] | None,
) -> list[str]:
    """Soft PRIORITY_CONCEPTS hints only (A.2) — checklist uses ``concept`` key."""
    if not must_cover_checklist:
        return []
    names: list[str] = []
    for item in must_cover_checklist:
        if not isinstance(item, dict):
            continue
        name = item.get("concept_name") or item.get("concept")
        if name and str(name).strip():
            names.append(str(name).strip())
    return names


def build_knowledge_user_payload(
    chunk_text: str,
    priority_concepts: list[str],
    *,
    previous_chunk_ended_mid_thought: bool = False,
    retention_retry: bool = False,
    content_gap_retry: bool = False,
) -> str:
    parts: list[str] = []
    if previous_chunk_ended_mid_thought:
        parts.append("PREVIOUS_CHUNK_ENDED_MID_THOUGHT: true")
        parts.append(
            "The prior chunk ended mid-thought. Complete only what appears in "
            "SOURCE_CHUNK below; do not invent the missing half.\n"
        )
    concepts_block = (
        ", ".join(priority_concepts) if priority_concepts else "(none provided)"
    )
    parts.append(f"PRIORITY_CONCEPTS: {concepts_block}\n\nSOURCE_CHUNK:\n{chunk_text}")
    if retention_retry:
        if content_gap_retry:
            parts.append(_CONTENT_GAP_RETRY_REMINDER)
        else:
            parts.append(_RETENTION_RETRY_REMINDER)
    return "\n".join(parts)


def _min_distill_note_tokens(chunk_text: str) -> int:
    chunk_tokens = rough_token_count(chunk_text)
    ratio_floor = int(
        external_research_settings.external_research_min_distill_keep_ratio
        * chunk_tokens
    )
    return max(
        external_research_settings.external_research_min_distill_note_tokens,
        ratio_floor,
    )


def _should_retry_for_content_gap(chunk_text: str, notes: str) -> bool:
    if not external_research_settings.external_research_distill_content_retention_retry:
        return False
    return source_has_high_risk_content(chunk_text) and notes_missing_high_risk(
        chunk_text, notes
    )


def _prefer_retry_notes(
    chunk_text: str,
    notes: str,
    continues: bool,
    retry_notes: str,
    retry_continues: bool,
    *,
    content_gap: bool,
) -> tuple[str, bool]:
    """Prefer the attempt that reduces high-risk gap; else prefer longer notes."""
    if content_gap or source_has_high_risk_content(chunk_text):
        first_gap = high_risk_gap_count(chunk_text, notes)
        retry_gap = high_risk_gap_count(chunk_text, retry_notes)
        if retry_gap < first_gap:
            return retry_notes, retry_continues
        if retry_gap > first_gap:
            return notes, continues

    if rough_token_count(retry_notes) >= rough_token_count(notes):
        return retry_notes, retry_continues
    return notes, continues


async def _call_distill_chunk(
    *,
    prompt_template: str,
    model: str,
    chunk_text: str,
    priority_concepts: list[str],
    previous_chunk_ended_mid_thought: bool,
    retention_retry: bool,
    content_gap_retry: bool = False,
) -> GroqCallResult:
    return await call_groq_with_rotation(
        messages=[
            SystemMessage(content=prompt_template),
            HumanMessage(
                content=build_knowledge_user_payload(
                    chunk_text,
                    priority_concepts,
                    previous_chunk_ended_mid_thought=previous_chunk_ended_mid_thought,
                    retention_retry=retention_retry,
                    content_gap_retry=content_gap_retry,
                )
            ),
        ],
        model=model,
        temperature=0.0,
        timeout=120,
        graph_node="external_research_knowledge_distillation",
        response_format={"type": "json_object"},
    )


def _parse_distill_response(content: str) -> tuple[str | None, bool]:
    parsed = parse_json_object(content)
    if not parsed:
        return None, False
    notes = parsed.get("knowledge_notes")
    if not notes or not str(notes).strip():
        return None, False
    continues = bool(parsed.get("continues_next_chunk"))
    return str(notes).strip(), continues


async def _distill_single_chunk(
    *,
    prompt_template: str,
    model: str,
    chunk_text: str,
    priority_concepts: list[str],
    previous_chunk_ended_mid_thought: bool,
) -> tuple[str | None, bool]:
    result = await _call_distill_chunk(
        prompt_template=prompt_template,
        model=model,
        chunk_text=chunk_text,
        priority_concepts=priority_concepts,
        previous_chunk_ended_mid_thought=previous_chunk_ended_mid_thought,
        retention_retry=False,
    )
    if not result.ok or not result.content:
        return None, False

    notes, continues = _parse_distill_response(result.content)
    if not notes:
        return None, False

    min_tokens = _min_distill_note_tokens(chunk_text)
    too_short = rough_token_count(notes) < min_tokens
    content_gap = _should_retry_for_content_gap(chunk_text, notes)

    if not too_short and not content_gap:
        return notes, continues

    retry = await _call_distill_chunk(
        prompt_template=prompt_template,
        model=model,
        chunk_text=chunk_text,
        priority_concepts=priority_concepts,
        previous_chunk_ended_mid_thought=previous_chunk_ended_mid_thought,
        retention_retry=True,
        content_gap_retry=content_gap,
    )
    if not retry.ok or not retry.content:
        return notes, continues

    retry_notes, retry_continues = _parse_distill_response(retry.content)
    if not retry_notes:
        return notes, continues

    return _prefer_retry_notes(
        chunk_text,
        notes,
        continues,
        retry_notes,
        retry_continues,
        content_gap=content_gap,
    )


async def distill_chunked_pages(
    chunked_pages: list[dict[str, Any]],
    *,
    domain: str | None,
    priority_concepts: list[str],
    should_continue: ShouldContinueAsync | None = None,
) -> tuple[list[dict[str, Any]], str]:
    """Run per-chunk knowledge distillation. Failed pages are dropped (A.8 / §14)."""
    prompt_template = DISTILLATION_PROMPTS_BY_DOMAIN.get(
        domain or "Mixed",
        MIXED_DISTILLATION_PROMPT,
    )
    model = llm_settings.llm_model
    distilled_pages: list[dict[str, Any]] = []

    for page in chunked_pages:
        await abort_if_should_stop(should_continue)
        chunks = page.get("chunks") or []
        if not isinstance(chunks, list) or not chunks:
            continue

        chunk_notes: list[str] = []
        page_failed = False
        previous_continues = False
        for chunk in chunks:
            await abort_if_should_stop(should_continue)
            chunk_text = str(chunk)
            notes, continues = await _distill_single_chunk(
                prompt_template=prompt_template,
                model=model,
                chunk_text=chunk_text,
                priority_concepts=priority_concepts,
                previous_chunk_ended_mid_thought=previous_continues,
            )
            if not notes:
                logger.warning(
                    "Knowledge distillation failed for url=%s",
                    page.get("url"),
                )
                page_failed = True
                break
            chunk_notes.append(notes)
            previous_continues = continues

        if page_failed or not chunk_notes:
            continue

        distilled_pages.append(
            {
                "url": page.get("url"),
                "notes": chunk_notes,
                "was_chunked": bool(page.get("was_chunked")),
            }
        )

    return distilled_pages, model
