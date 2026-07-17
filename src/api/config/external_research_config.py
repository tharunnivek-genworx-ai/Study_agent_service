"""External Research Mode settings (Tavily search, extraction, merge floors)."""

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Design §5.2 starting blocklist — extend via EXTERNAL_RESEARCH_DOMAIN_BLOCKLIST.
_DEFAULT_DOMAIN_BLOCKLIST: list[str] = [
    # low-signal / SEO content farms & forums
    "quora.com",
    "pinterest.com",
    "reddit.com",
    "medium.com",
    "linkedin.com",
    "facebook.com",
    "instagram.com",
    "tiktok.com",
    "x.com",
    "twitter.com",
    # answer-farm / low-quality tutorial mills that extract poorly
    "brainly.com",
    "coursehero.com",
    "chegg.com",
    "studocu.com",
    "scribd.com",
    "slideshare.net",
    # link aggregators, not primary content
    "youtube.com",
    # Q&A / course landings — low signal for teaching-prep extraction
    "stackexchange.com",
    "stackoverflow.com",
    "codecademy.com",
    "udemy.com",
    "coursera.org",
]


class ExternalResearchSettings(BaseSettings):
    """Worker-side External Research tunables loaded from environment variables."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    tavily_api_key: str = ""

    external_research_domain_blocklist: list[str] = Field(
        default_factory=lambda: list(_DEFAULT_DOMAIN_BLOCKLIST),
    )
    external_research_max_search_results: int = 5
    external_research_target_results: int = 3
    external_research_min_extraction_tokens: int = 200
    external_research_chunk_token_threshold: int = 3000
    external_research_min_merge_tokens: int = 800
    external_research_min_distill_note_tokens: int = 120
    external_research_min_distill_keep_ratio: float = 0.08
    external_research_distill_content_retention_retry: bool = True
    external_research_page_fetch_timeout_seconds: int = 10

    @field_validator("external_research_domain_blocklist", mode="before")
    @classmethod
    def _parse_domain_blocklist(cls, value: object) -> object:
        """Accept JSON arrays, or comma/semicolon/whitespace-separated domain lists."""
        if value is None or value == "":
            return list(_DEFAULT_DOMAIN_BLOCKLIST)
        if isinstance(value, str):
            stripped = value.strip()
            if stripped.startswith("["):
                return value
            separators = [";", ",", "\n"]
            for sep in separators:
                if sep in stripped:
                    return [
                        part.strip() for part in stripped.split(sep) if part.strip()
                    ]
            return [stripped] if stripped else list(_DEFAULT_DOMAIN_BLOCKLIST)
        return value


external_research_settings = ExternalResearchSettings()
