"""Cross-website merge via call_groq_with_rotation (design §11)."""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from src.api.config import external_research_settings, llm_settings
from src.api.control.study_agent.prompts.external_research import (
    CROSS_WEBSITE_MERGE_PROMPT,
)
from src.api.utils.external_research_utils.abort import (
    ShouldContinueAsync,
    abort_if_should_stop,
)
from src.api.utils.external_research_utils.json_parse import parse_json_object
from src.api.utils.external_research_utils.tokens import rough_token_count
from src.api.utils.LLM_utils.groq_retry import GroqCallResult, call_groq_with_rotation

logger = logging.getLogger(__name__)

_SHORT_MERGE_RETRY_SUFFIX = (
    "\n\nREMINDER: Your previous merged output was too short. UNION all unique "
    "facts from every source summary. Restore dropped code blocks, equations, "
    "dates, and named entities. Do not re-summarize into an overview."
)


def _build_merge_user_payload(
    priority_concepts: list[str],
    website_summaries: str,
    *,
    retry_on_short: bool = False,
) -> str:
    concepts_block = (
        ", ".join(priority_concepts) if priority_concepts else "(none provided)"
    )
    payload = f"PRIORITY_CONCEPTS: {concepts_block}\n\n{website_summaries}"
    if retry_on_short:
        payload += _SHORT_MERGE_RETRY_SUFFIX
    return payload


async def _call_merge_llm(
    *,
    priority_concepts: list[str],
    website_summaries: str,
    retry_on_short: bool,
) -> GroqCallResult:
    return await call_groq_with_rotation(
        messages=[
            SystemMessage(content=CROSS_WEBSITE_MERGE_PROMPT),
            HumanMessage(
                content=_build_merge_user_payload(
                    priority_concepts,
                    website_summaries,
                    retry_on_short=retry_on_short,
                )
            ),
        ],
        model=llm_settings.llm_model,
        temperature=0.0,
        timeout=120,
        graph_node="external_research_cross_website_merge",
        response_format={"type": "json_object"},
    )


def _parse_merge_response(content: str) -> str:
    parsed = parse_json_object(content)
    merged_text = (parsed or {}).get("ground_truth_reference") if parsed else None
    return str(merged_text).strip() if merged_text else ""


def effective_merge_min_tokens(source_summaries: list[str]) -> int:
    """Scale the merge floor to available source notes; cap at configured max.

    When KD-compressed notes are short, requiring a fixed 800-token merge forces
    either hallucination or fail-soft. Scale to ``source_tokens * ratio``, keep an
    absolute floor, and never exceed ``external_research_min_merge_tokens``.
    """
    cap = external_research_settings.external_research_min_merge_tokens
    absolute = external_research_settings.external_research_min_merge_absolute_tokens
    ratio = external_research_settings.external_research_merge_input_ratio
    source_tokens = sum(rough_token_count(text) for text in source_summaries)
    if source_tokens <= 0:
        return absolute
    scaled = int(source_tokens * ratio)
    return max(absolute, min(cap, scaled))


def _fail_soft_below_min() -> dict[str, Any]:
    return {
        "external_research_status": "fail_soft",
        "external_research_fail_reason": "merged_output_below_min_tokens",
        "ground_truth_reference": None,
        "external_source_urls": [],
    }


def _best_available_fallback(
    reduced_pages: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """Keep the strongest single-source notes when merge cannot clear the floor."""
    min_keep = external_research_settings.external_research_min_best_available_tokens
    ranked: list[tuple[int, dict[str, Any]]] = []
    for page in reduced_pages:
        summary = str(page.get("website_summary") or "").strip()
        if not summary:
            continue
        ranked.append((rough_token_count(summary), page))
    if not ranked:
        return None

    ranked.sort(key=lambda item: item[0], reverse=True)
    best_tokens, best_page = ranked[0]
    if best_tokens < min_keep:
        return None

    url = str(best_page.get("url") or "").strip()
    summary = str(best_page.get("website_summary") or "").strip()
    logger.info(
        "Merge below floor; using best-available source (%d tokens): %s",
        best_tokens,
        url or "(missing url)",
    )
    return {
        "external_research_status": "success",
        "external_research_fail_reason": None,
        "ground_truth_reference": summary,
        "external_source_urls": [url] if url else [],
    }


def _success_payload(
    merged_text: str,
    reduced_pages: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "external_research_status": "success",
        "external_research_fail_reason": None,
        "ground_truth_reference": merged_text,
        "external_source_urls": [
            str(page.get("url")) for page in reduced_pages if page.get("url")
        ],
    }


async def merge_website_summaries(
    reduced_pages: list[dict[str, Any]],
    *,
    priority_concepts: list[str],
    should_continue: ShouldContinueAsync | None = None,
) -> dict[str, Any]:
    """Merge per-site summaries into ground_truth_reference or fail_soft.

    On short/failed merge, prefer a best-available single source over discarding
    all research notes.
    """
    await abort_if_should_stop(should_continue)

    if not reduced_pages:
        return {
            "external_research_status": "fail_soft",
            "external_research_fail_reason": "all_extractions_failed",
            "ground_truth_reference": None,
            "external_source_urls": [],
        }

    summaries = [str(page.get("website_summary") or "") for page in reduced_pages]
    min_tokens = effective_merge_min_tokens(summaries)
    website_summaries = "\n\n===\n\n".join(
        f"SOURCE: {page.get('url')}\n{page.get('website_summary')}"
        for page in reduced_pages
    )

    result = await _call_merge_llm(
        priority_concepts=priority_concepts,
        website_summaries=website_summaries,
        retry_on_short=False,
    )

    if not result.ok or not result.content:
        logger.warning("Cross-website merge LLM failed: %s", result.error_type)
        fallback = _best_available_fallback(reduced_pages)
        return fallback if fallback is not None else _fail_soft_below_min()

    merged_text = _parse_merge_response(result.content)

    if rough_token_count(merged_text) < min_tokens:
        retry = await _call_merge_llm(
            priority_concepts=priority_concepts,
            website_summaries=website_summaries,
            retry_on_short=True,
        )
        if retry.ok and retry.content:
            retry_text = _parse_merge_response(retry.content)
            if rough_token_count(retry_text) >= rough_token_count(merged_text):
                merged_text = retry_text

        if rough_token_count(merged_text) < min_tokens:
            fallback = _best_available_fallback(reduced_pages)
            if fallback is not None:
                return fallback
            return _fail_soft_below_min()

    return _success_payload(merged_text, reduced_pages)
