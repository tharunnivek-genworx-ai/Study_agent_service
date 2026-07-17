"""Search blocklist, URL demotion, PDF hard-exclude, and short-result retry."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from src.api.config.external_research_config import _DEFAULT_DOMAIN_BLOCKLIST
from src.api.utils.external_research_utils.content_extraction import (
    extract_pages_from_urls,
    extract_single_page,
    is_marketing_dense,
)
from src.api.utils.external_research_utils.search import (
    extract_domain,
    has_non_legacy_alternate,
    is_demoted_url,
    is_excluded_url,
    search_external_urls,
    select_urls_with_domain_dedupe,
)


def test_default_blocklist_includes_course_and_qa_domains():
    for domain in (
        "stackexchange.com",
        "stackoverflow.com",
        "codecademy.com",
        "udemy.com",
        "coursera.org",
    ):
        assert domain in _DEFAULT_DOMAIN_BLOCKLIST


def test_is_demoted_url_for_course_paths():
    urls = [
        "https://www.codecademy.com/learn/react-hooks",
        "https://react.dev/reference/react/useState",
    ]
    assert is_demoted_url(urls[0], urls) is True
    assert is_demoted_url(urls[1], urls) is False


@pytest.mark.parametrize(
    "url",
    [
        "https://example.edu/papers/wave-particle.pdf",
        "https://arxiv.org/pdf/1234.5678",
        "https://example.com/doc?filetype=pdf",
        "https://example.com/download?format=pdf",
    ],
)
def test_is_excluded_url_for_pdfs(url: str):
    assert is_excluded_url(url) is True
    assert is_demoted_url(url, [url]) is False


def test_pdfs_are_excluded_not_demoted():
    """PDFs are hard-excluded; is_demoted_url returns False for them."""
    urls = [
        "https://example.edu/papers/wave-particle.pdf",
        "https://en.wikipedia.org/wiki/Wave%E2%80%93particle_duality",
    ]
    assert is_excluded_url(urls[0]) is True
    assert is_demoted_url(urls[0], urls) is False
    assert is_demoted_url(urls[1], urls) is False


def test_legacy_host_demoted_when_non_legacy_alternate_exists():
    urls = [
        "https://legacy.reactjs.org/docs/hooks-intro.html",
        "https://react.dev/reference/react/useState",
    ]
    assert has_non_legacy_alternate(urls[0], urls) is True
    assert is_demoted_url(urls[0], urls) is True


def test_legacy_host_not_demoted_when_no_alternate_in_set():
    urls = ["https://legacy.reactjs.org/docs/hooks-intro.html"]
    assert has_non_legacy_alternate(urls[0], urls) is False
    assert is_demoted_url(urls[0], urls) is False


def test_select_urls_prefers_non_demoted_and_dedupes_domains():
    urls = [
        "https://www.codecademy.com/learn/react-hooks",
        "https://react.dev/reference/react/useState",
        "https://react.dev/learn/state-a-hook",
        "https://developer.mozilla.org/en-US/docs/Web/JavaScript",
    ]
    selected = select_urls_with_domain_dedupe(urls, target=3)
    assert selected[0] == "https://react.dev/reference/react/useState"
    assert "codecademy.com" not in extract_domain(selected[0])
    assert len({extract_domain(url) for url in selected}) == len(selected)
    assert len(selected) == 3


def test_select_urls_hard_excludes_pdfs_never_fills_with_them():
    urls = [
        "https://arxiv.org/pdf/1234.5678.pdf",
        "https://en.wikipedia.org/wiki/Wave%E2%80%93particle_duality",
        "https://plato.stanford.edu/entries/qt-quantlog/",
    ]
    selected = select_urls_with_domain_dedupe(urls, target=2)
    assert selected == [
        "https://en.wikipedia.org/wiki/Wave%E2%80%93particle_duality",
        "https://plato.stanford.edu/entries/qt-quantlog/",
    ]


def test_select_urls_returns_empty_when_only_pdfs():
    urls = [
        "https://arxiv.org/pdf/1234.5678.pdf",
        "https://example.edu/notes/lecture.pdf",
    ]
    assert select_urls_with_domain_dedupe(urls, target=3) == []


def test_select_urls_uses_demoted_when_needed_to_fill_target():
    urls = [
        "https://www.codecademy.com/learn/react-hooks",
        "https://www.udemy.com/course/react-hooks/",
    ]
    selected = select_urls_with_domain_dedupe(urls, target=2)
    assert len(selected) == 2
    assert selected == urls


def test_search_external_urls_uses_topic_subtopic_query_only():
    mock_client = MagicMock()
    mock_client.search.return_value = {
        "results": [
            {"url": "https://react.dev/reference/react/useState"},
            {"url": "https://developer.mozilla.org/en-US/docs/Web/JavaScript"},
            {"url": "https://en.wikipedia.org/wiki/React_(software)"},
        ]
    }

    urls = search_external_urls(
        "React Hooks",
        tavily_client=mock_client,
    )

    assert urls == [
        "https://react.dev/reference/react/useState",
        "https://developer.mozilla.org/en-US/docs/Web/JavaScript",
        "https://en.wikipedia.org/wiki/React_(software)",
    ]
    mock_client.search.assert_called_once()
    kwargs = mock_client.search.call_args.kwargs
    assert kwargs["query"] == "React Hooks"
    assert kwargs["exclude_domains"] is not None
    assert "codecademy.com" in kwargs["exclude_domains"]
    assert kwargs["include_raw_content"] is False


def test_search_external_urls_retries_when_first_pass_is_mostly_pdfs():
    mock_client = MagicMock()
    mock_client.search.side_effect = [
        {
            "results": [
                {"url": "https://arxiv.org/pdf/1234.5678.pdf"},
                {"url": "https://example.edu/notes/lecture.pdf"},
                {"url": "https://react.dev/reference/react/useState"},
            ]
        },
        {
            "results": [
                {"url": "https://developer.mozilla.org/en-US/docs/Web/JavaScript"},
                {"url": "https://en.wikipedia.org/wiki/React_(software)"},
                {"url": "https://react.dev/learn/thinking-in-react"},
            ]
        },
    ]

    urls = search_external_urls("React Hooks", tavily_client=mock_client)

    assert mock_client.search.call_count == 2
    first_kwargs = mock_client.search.call_args_list[0].kwargs
    second_kwargs = mock_client.search.call_args_list[1].kwargs
    assert first_kwargs["query"] == "React Hooks"
    assert "-filetype:pdf" in second_kwargs["query"]
    assert second_kwargs["max_results"] > first_kwargs["max_results"]
    assert "https://arxiv.org/pdf/1234.5678.pdf" not in urls
    assert "https://react.dev/reference/react/useState" in urls
    assert len(urls) == 3


def test_search_external_urls_no_retry_when_target_already_met():
    mock_client = MagicMock()
    mock_client.search.return_value = {
        "results": [
            {"url": "https://react.dev/reference/react/useState"},
            {"url": "https://developer.mozilla.org/en-US/docs/Web/JavaScript"},
            {"url": "https://en.wikipedia.org/wiki/React_(software)"},
        ]
    }

    urls = search_external_urls("React Hooks", tavily_client=mock_client)
    assert len(urls) == 3
    mock_client.search.assert_called_once()


def test_search_external_urls_returns_empty_on_api_error():
    mock_client = MagicMock()
    mock_client.search.side_effect = RuntimeError("tavily down")

    assert search_external_urls("React Hooks", tavily_client=mock_client) == []


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (
            "Skill level beginner. Certificate of completion. "
            "50,000 learners enrolled. Unlock additional features.",
            True,
        ),
        (
            "The Rules of Hooks require that hooks are called at the top level.",
            False,
        ),
        (
            "Skill level beginner. Time to complete 5 hours. Projects 1.",
            False,
        ),
    ],
)
def test_is_marketing_dense(text: str, expected: bool) -> None:
    assert is_marketing_dense(text) is expected


def test_extract_pages_from_urls_drops_marketing_dense_pages(monkeypatch):
    marketing_body = (
        "Learn React Hooks today. Skill level beginner. "
        "Certificate of completion available. 50,000 learners enrolled. "
        "Unlock additional features for Pro members. " * 20
    )

    monkeypatch.setattr(
        "src.api.utils.external_research_utils.content_extraction.extract_single_page",
        lambda url: marketing_body,
    )

    assert (
        extract_pages_from_urls(["https://www.codecademy.com/learn/react-hooks"]) == []
    )


def test_extract_pages_from_urls_keeps_teaching_article(monkeypatch):
    article = "The Rules of Hooks are essential. " * 40

    monkeypatch.setattr(
        "src.api.utils.external_research_utils.content_extraction.extract_single_page",
        lambda url: article,
    )

    pages = extract_pages_from_urls(["https://react.dev/reference/react/hooks"])
    assert len(pages) == 1
    assert pages[0]["url"] == "https://react.dev/reference/react/hooks"


def test_extract_single_page_skips_pdf_urls_without_fetch():
    assert extract_single_page("https://example.edu/notes/lecture.pdf") is None
