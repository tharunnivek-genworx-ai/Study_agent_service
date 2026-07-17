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


def _fail_soft_below_min() -> dict[str, Any]:
    return {
        "external_research_status": "fail_soft",
        "external_research_fail_reason": "merged_output_below_min_tokens",
        "ground_truth_reference": None,
        "external_source_urls": [],
    }


async def merge_website_summaries(
    reduced_pages: list[dict[str, Any]],
    *,
    priority_concepts: list[str],
    should_continue: ShouldContinueAsync | None = None,
) -> dict[str, Any]:
    """Merge per-site summaries into ground_truth_reference or fail_soft."""
    await abort_if_should_stop(should_continue)

    if not reduced_pages:
        return {
            "external_research_status": "fail_soft",
            "external_research_fail_reason": "all_extractions_failed",
            "ground_truth_reference": None,
            "external_source_urls": [],
        }

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
        return _fail_soft_below_min()

    merged_text = _parse_merge_response(result.content)
    min_tokens = external_research_settings.external_research_min_merge_tokens

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
            return _fail_soft_below_min()

    return {
        "external_research_status": "success",
        "external_research_fail_reason": None,
        "ground_truth_reference": merged_text,
        "external_source_urls": [
            str(page.get("url")) for page in reduced_pages if page.get("url")
        ],
    }
