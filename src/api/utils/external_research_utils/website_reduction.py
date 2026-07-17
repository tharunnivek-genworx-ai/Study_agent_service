"""Website reduction via call_groq_with_rotation (design §10)."""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage

from src.api.config import llm_settings
from src.api.control.study_agent.prompts.external_research import (
    WEBSITE_REDUCTION_PROMPT,
)
from src.api.utils.external_research_utils.abort import (
    ShouldContinueAsync,
    abort_if_should_stop,
)
from src.api.utils.external_research_utils.json_parse import parse_json_object
from src.api.utils.LLM_utils.groq_retry import call_groq_with_rotation

logger = logging.getLogger(__name__)


async def reduce_distilled_pages(
    distilled_pages: list[dict[str, Any]],
    *,
    should_continue: ShouldContinueAsync | None = None,
) -> list[dict[str, Any]]:
    """Merge chunk notes per page; single-note pages pass through without an LLM call."""
    model = llm_settings.llm_model
    reduced_pages: list[dict[str, Any]] = []

    for page in distilled_pages:
        await abort_if_should_stop(should_continue)
        notes = page.get("notes") or []
        if not isinstance(notes, list) or not notes:
            continue

        # Gate on note count, not was_chunked — a false was_chunked with one note
        # must not trigger a destructive rewrite into a shorter overview.
        if len(notes) <= 1:
            reduced_pages.append(
                {
                    "url": page.get("url"),
                    "website_summary": str(notes[0]),
                }
            )
            continue

        combined_notes = "\n\n---\n\n".join(str(note) for note in notes)
        result = await call_groq_with_rotation(
            messages=[
                SystemMessage(content=WEBSITE_REDUCTION_PROMPT),
                HumanMessage(content=f"CHUNK_NOTES:\n{combined_notes}"),
            ],
            model=model,
            temperature=0.0,
            timeout=120,
            graph_node="external_research_website_reduction",
            response_format={"type": "json_object"},
        )
        if not result.ok or not result.content:
            logger.warning(
                "Website reduction failed for url=%s — using joined notes",
                page.get("url"),
            )
            reduced_pages.append(
                {
                    "url": page.get("url"),
                    "website_summary": combined_notes,
                }
            )
            continue

        parsed = parse_json_object(result.content)
        summary = (parsed or {}).get("website_summary") if parsed else None
        if not summary or not str(summary).strip():
            summary = combined_notes
        reduced_pages.append(
            {
                "url": page.get("url"),
                "website_summary": str(summary).strip(),
            }
        )

    return reduced_pages
