"""Backward-compatible re-export — prefer ``prompts.parsing.llama_parse_prompt``."""

from src.api.control.study_agent.prompts.parsing.llama_parse_prompt import (
    LLAMAPARSE_PARSING_INSTRUCTION,
    build_parsing_instruction,
)

__all__ = [
    "LLAMAPARSE_PARSING_INSTRUCTION",
    "build_parsing_instruction",
]
