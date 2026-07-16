"""LLM provider keys, models, and token limits for the Study Agent Service."""

from typing import Self

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class LLMSettings(BaseSettings):
    """Groq / LlamaParse configuration loaded from environment variables."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Groq API keys (rotation pool) — GROQ_API_KEY through GROQ_API_KEY_10
    groq_api_key: str = ""
    groq_api_key_2: str = ""
    groq_api_key_3: str = ""
    groq_api_key_4: str = ""
    groq_api_key_5: str = ""
    groq_api_key_6: str = ""
    groq_api_key_7: str = ""
    groq_api_key_8: str = ""
    groq_api_key_9: str = ""
    groq_api_key_10: str = ""

    def groq_api_keys(self) -> list[str]:
        """Return all configured Groq API keys in rotation order."""
        return [
            key
            for key in (
                self.groq_api_key,
                self.groq_api_key_2,
                self.groq_api_key_3,
                self.groq_api_key_4,
                self.groq_api_key_5,
                self.groq_api_key_6,
                self.groq_api_key_7,
                self.groq_api_key_8,
                self.groq_api_key_9,
                self.groq_api_key_10,
            )
            if key
        ]

    # LlamaParse reference extraction
    llama_parse_api_key: str = ""

    # Model selection — default reused by generation, QC, and checklist.
    default_llm_model: str = "llama-3.3-70b-versatile"
    llm_model: str = ""
    qc_llm_model: str = ""
    checklist_llm_model: str = ""

    # Study material generation — first draft / full regen from generation prompt
    study_generation_temperature: float = 0.25
    study_generation_top_p: float = 0.9
    study_generation_do_sample: bool = True

    # Study material improve / regenerate / section patch-insert
    study_revision_temperature: float = 0.35
    study_revision_top_p: float = 0.9
    study_revision_do_sample: bool = True

    # Quiz question generation
    quiz_generation_temperature: float = 0.4

    # Hint generation
    hint_generation_temperature: float = 0.4

    # QC verification — study docs and quiz (deterministic rubric evaluation)
    qc_temperature: float = 0.0
    qc_top_p: float = 1.0
    qc_do_sample: bool = False

    # QC token budgets (Groq on_demand TPM counts input + max_tokens per request)
    qc_llm_max_tokens: int = 4096
    quiz_qc_llm_max_tokens: int = 8192
    quiz_generation_llm_max_tokens: int = 16384
    groq_qc_tpm_limit: int = 12000
    qc_document_max_chars: int = 80000

    # Retry behaviour
    llm_retry_attempts: int = 3
    hint_quality_max_retries: int = 2

    @model_validator(mode="after")
    def _resolve_llm_models(self) -> Self:
        default = self.default_llm_model
        if not self.llm_model:
            self.llm_model = default
        if not self.qc_llm_model:
            self.qc_llm_model = default
        if not self.checklist_llm_model:
            self.checklist_llm_model = default
        return self


llm_settings = LLMSettings()
