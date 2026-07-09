"""Shared constants for study material quality checking."""

from __future__ import annotations

from src.api.schemas.qc_schemas import (
    CODE_CATEGORIES,
)
from src.api.utils.space_node_utils.build_node import NO_INSTRUCTION_FALLBACK

MAX_QC_ATTEMPTS = 3
MAX_GENERATOR_FORMAT_ATTEMPTS = 3
MAX_VERIFICATION_PARSE_RETRIES = 1

DEFAULT_INSTRUCTION = NO_INSTRUCTION_FALLBACK

FROZEN_SECTION_CATEGORIES = CODE_CATEGORIES
