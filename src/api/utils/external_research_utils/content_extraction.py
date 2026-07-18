"""Per-URL page extraction via trafilatura / readability (design §6)."""

from __future__ import annotations

import logging
import re
from typing import Any

import httpx

from src.api.config import external_research_settings
from src.api.utils.external_research_utils.search import is_excluded_url
from src.api.utils.external_research_utils.tokens import rough_token_count

logger = logging.getLogger(__name__)

_MARKETING_DENSITY_SIGNALS = (
    "learners enrolled",
    "certificate of completion",
    "skill level",
    "unlock additional features",
)


def is_marketing_dense(text: str, *, min_signals: int = 3) -> bool:
    """True when cleaned/extracted text looks like a course landing, not an article."""
    lower = text.lower()
    hits = sum(1 for signal in _MARKETING_DENSITY_SIGNALS if signal in lower)
    return hits >= min_signals


def _readability_fallback(html: str) -> str | None:
    try:
        from readability import Document as ReadabilityDocument

        doc = ReadabilityDocument(html)
        summary_html = doc.summary()
        text = re.sub(r"<[^>]+>", " ", summary_html)
        text = re.sub(r"\s+", " ", text).strip()
        return text or None
    except Exception:
        return None


def extract_single_page(url: str) -> str | None:
    """Fetch and extract main text for one URL. Never raises."""
    if is_excluded_url(url):
        logger.info("Skipped excluded URL (PDF or non-HTML): %s", url)
        return None

    timeout = external_research_settings.external_research_page_fetch_timeout_seconds
    try:
        with httpx.Client(
            timeout=timeout,
            follow_redirects=True,
            headers={"User-Agent": "StudyGuruExternalResearch/1.0"},
        ) as client:
            response = client.get(url)
            response.raise_for_status()
            content_type = (response.headers.get("content-type") or "").lower()
            if "application/pdf" in content_type:
                logger.info("Skipped PDF Content-Type for %s", url)
                return None
            downloaded = response.text
    except Exception:
        logger.info("Page fetch failed for %s", url, exc_info=True)
        return None

    if not downloaded:
        return None

    try:
        import trafilatura

        text = trafilatura.extract(
            downloaded,
            url=url,
            favor_precision=True,
            include_tables=True,
            include_formatting=False,
            include_comments=False,
            include_images=False,
            include_links=False,
            deduplicate=True,
            output_format="txt",
        )
        if text and text.strip():
            return str(text)
        return _readability_fallback(downloaded)
    except Exception:
        logger.info("Extraction failed for %s", url, exc_info=True)
        return None


def extract_pages_from_urls(urls: list[str]) -> list[dict[str, Any]]:
    """Extract pages meeting the min-token floor. Thin/failed pages are dropped."""
    min_tokens = external_research_settings.external_research_min_extraction_tokens
    extracted: list[dict[str, Any]] = []
    for url in urls:
        text = extract_single_page(url)
        if not text:
            continue
        if is_marketing_dense(text):
            logger.info("Dropped marketing-dense page after extraction: %s", url)
            continue
        if rough_token_count(text) >= min_tokens:
            extracted.append({"url": url, "raw_text": text})
    return extracted


def extract_pages_until_target(
    urls: list[str],
    *,
    target: int | None = None,
) -> list[dict[str, Any]]:
    """Try candidate URLs in order until ``target`` successful pages are collected.

    When a URL fails extract / is thin / marketing-dense, continue with the next
    candidate from the search refill pool instead of stopping early.
    """
    goal = (
        target
        if target is not None
        else external_research_settings.external_research_target_results
    )
    if goal <= 0:
        return []

    extracted: list[dict[str, Any]] = []
    for url in urls:
        if len(extracted) >= goal:
            break
        page_batch = extract_pages_from_urls([url])
        if not page_batch:
            logger.info("Extraction dropped URL; trying next candidate: %s", url)
            continue
        extracted.extend(page_batch)
    return extracted
