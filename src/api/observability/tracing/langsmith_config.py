# src/api/observability/tracing/langsmith_config.py
"""LangSmith tracing configuration and initialization."""

import os

import dotenv


def init_langsmith_tracing() -> None:
    """Initialize LangSmith tracing environment variables by loading the .env file.

    Maps LANGSMITH_* environment variables to the standard LANGCHAIN_* equivalents.
    """
    dotenv.load_dotenv()

    # Enable tracing if LANGSMITH_TRACING is set to true
    if os.getenv("LANGSMITH_TRACING") == "true":
        os.environ["LANGCHAIN_TRACING_V2"] = "true"

    # Map other variables
    if api_key := os.getenv("LANGSMITH_API_KEY"):
        os.environ["LANGCHAIN_API_KEY"] = api_key
    if endpoint := os.getenv("LANGSMITH_ENDPOINT"):
        os.environ["LANGCHAIN_ENDPOINT"] = endpoint
    if project := os.getenv("LANGSMITH_PROJECT"):
        os.environ["LANGCHAIN_PROJECT"] = project
