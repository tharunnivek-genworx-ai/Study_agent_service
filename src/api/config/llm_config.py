"""LLM provider keys, models, and token limits for the Study Agent Service."""

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

    # Model selection
    # Groq Llama 70B — study material generation
    llm_model: str = "llama-3.3-70b-versatile"
    # Groq Llama 70B — study material QC verification
    qc_llm_model: str = "llama-3.3-70b-versatile"
    # Groq Llama 8B — concept checklist
    checklist_llm_model: str = "llama-3.1-8b-instant"

    # QC token budgets (Groq on_demand TPM counts input + max_tokens per request)
    qc_llm_max_tokens: int = 4096
    quiz_qc_llm_max_tokens: int = 8192
    groq_qc_tpm_limit: int = 12000
    qc_document_max_chars: int = 80000

    # Retry behaviour
    llm_retry_attempts: int = 3
    hint_quality_max_retries: int = 2


llm_settings = LLMSettings()
