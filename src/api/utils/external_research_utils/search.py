"""Tavily search with domain blocklist, PDF hard-exclude, and short-result retry."""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import parse_qs, urlparse

from src.api.config import external_research_settings

logger = logging.getLogger(__name__)

_LOW_SIGNAL_PATH_FRAGMENTS = ("/learn/", "/course/", "/courses/")
_PDF_QUERY_EXCLUSION = "-filetype:pdf"


def extract_domain(url: str) -> str:
    netloc = urlparse(url).netloc
    return netloc.replace("www.", "").lower()


def _is_low_signal_path(url: str) -> bool:
    path = urlparse(url).path.lower()
    return any(fragment in path for fragment in _LOW_SIGNAL_PATH_FRAGMENTS)


def _is_pdf_url(url: str) -> bool:
    """True for PDF links by extension, /pdf/ path, or common query flags."""
    parsed = urlparse(url)
    path = parsed.path.lower()
    if path.endswith(".pdf"):
        return True
    if "/pdf/" in path:
        return True
    query = parse_qs(parsed.query)
    for key in ("filetype", "format", "type", "download"):
        values = [str(v).lower() for v in query.get(key, [])]
        if any(v == "pdf" or v.endswith(".pdf") for v in values):
            return True
    return False


def is_excluded_url(url: str) -> bool:
    """Hard-reject URLs that must never be selected (PDFs are not extractable HTML)."""
    return _is_pdf_url(url)


def _is_legacy_host(url: str) -> bool:
    host = urlparse(url).netloc.replace("www.", "").lower()
    return host.startswith("legacy.")


def _legacy_host_suffix(url: str) -> str | None:
    host = urlparse(url).netloc.replace("www.", "").lower()
    if not host.startswith("legacy."):
        return None
    return host[len("legacy.") :]


def has_non_legacy_alternate(legacy_url: str, candidate_urls: list[str]) -> bool:
    """True when the result set includes at least one non-legacy URL to prefer instead."""
    if not _is_legacy_host(legacy_url):
        return False

    suffix = _legacy_host_suffix(legacy_url)
    for url in candidate_urls:
        if url == legacy_url:
            continue
        host = urlparse(url).netloc.replace("www.", "").lower()
        if host.startswith("legacy."):
            continue
        # Same registrable domain (legacy.reactjs.org ↔ reactjs.org)
        if suffix and (suffix in host or host.endswith(suffix)):
            return True
        # Any other non-legacy hit in the same Tavily result set is a usable alternate
        # (e.g. legacy.reactjs.org vs react.dev).
        return True
    return False


def is_demoted_url(url: str, candidate_urls: list[str]) -> bool:
    """Low-signal URLs are skipped unless needed to fill the target result count.

    PDFs are not demoted here — they are hard-excluded via ``is_excluded_url``.
    """
    if is_excluded_url(url):
        return False
    if _is_low_signal_path(url):
        return True
    if _is_legacy_host(url) and has_non_legacy_alternate(url, candidate_urls):
        return True
    return False


def select_urls_with_domain_dedupe(
    urls: list[str],
    *,
    target: int,
) -> list[str]:
    """Keep Tavily relevance order; drop PDFs; prefer non-demoted; dedupe by domain."""
    if not urls:
        return []

    eligible = [url for url in urls if not is_excluded_url(url)]
    if not eligible:
        return []

    demoted_flags = [is_demoted_url(url, eligible) for url in eligible]
    seen_domains: set[str] = set()
    selected: list[str] = []

    for prefer_demoted in (False, True):
        for url, is_demoted in zip(eligible, demoted_flags, strict=True):
            if is_demoted != prefer_demoted:
                continue
            domain = extract_domain(url)
            if not domain or domain in seen_domains:
                continue
            seen_domains.add(domain)
            selected.append(url)
            if len(selected) >= target:
                return selected

    return selected


def _merge_unique_urls(*batches: list[str]) -> list[str]:
    """Preserve first-seen order across search batches."""
    seen: set[str] = set()
    merged: list[str] = []
    for batch in batches:
        for url in batch:
            if url in seen:
                continue
            seen.add(url)
            merged.append(url)
    return merged


def _with_pdf_query_exclusion(query: str) -> str:
    if _PDF_QUERY_EXCLUSION.lower() in query.lower():
        return query
    return f"{query} {_PDF_QUERY_EXCLUSION}".strip()


def _urls_from_tavily_response(response: dict[str, Any] | None) -> list[str]:
    if not response or not isinstance(response, dict):
        return []
    results = response.get("results") or []
    if not isinstance(results, list):
        return []
    ordered_urls: list[str] = []
    for result in results:
        if not isinstance(result, dict):
            continue
        url = result.get("url")
        if url and isinstance(url, str):
            ordered_urls.append(url)
    return ordered_urls


def _tavily_search(
    tavily_client: Any,
    *,
    query: str,
    max_results: int,
) -> list[str]:
    try:
        response: dict[str, Any] = tavily_client.search(
            query=query,
            max_results=max_results,
            search_depth="basic",
            exclude_domains=(
                external_research_settings.external_research_domain_blocklist
            ),
            include_raw_content=False,
        )
    except Exception:
        logger.exception("Tavily search failed for query=%r", query)
        return []
    return _urls_from_tavily_response(response)


def search_external_urls(
    query: str,
    *,
    tavily_client: Any | None = None,
) -> list[str]:
    """Search Tavily; hard-drop PDFs; retry once when usable HTML URLs are short.

    Blocklisted domains are excluded by Tavily via ``exclude_domains``.
    PDFs are never selected. Course/legacy URLs remain demoted (fill last).
    If the first pass yields fewer than ``target_results`` non-PDF URLs, one
    retry runs with ``-filetype:pdf`` and a larger ``max_results`` pool.
    """
    search_query = query.strip()
    if not search_query:
        return []

    api_key = (external_research_settings.tavily_api_key or "").strip()
    if not api_key and tavily_client is None:
        logger.warning("TAVILY_API_KEY is not configured — external search skipped")
        return []

    if tavily_client is None:
        try:
            from tavily import TavilyClient

            tavily_client = TavilyClient(api_key=api_key)
        except Exception:
            logger.exception("Failed to construct TavilyClient")
            return []

    max_results = external_research_settings.external_research_max_search_results
    target = external_research_settings.external_research_target_results

    first_urls = _tavily_search(
        tavily_client,
        query=search_query,
        max_results=max_results,
    )
    selected = select_urls_with_domain_dedupe(first_urls, target=target)
    if len(selected) >= target:
        return selected

    retry_max = max(max_results + 3, target * 2)
    retry_query = _with_pdf_query_exclusion(search_query)
    logger.info(
        "External search short on usable URLs (%d/%d); retrying with query=%r max_results=%d",
        len(selected),
        target,
        retry_query,
        retry_max,
    )
    retry_urls = _tavily_search(
        tavily_client,
        query=retry_query,
        max_results=retry_max,
    )
    merged = _merge_unique_urls(first_urls, retry_urls)
    return select_urls_with_domain_dedupe(merged, target=target)
