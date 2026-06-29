"""Shared constants for study material quality checking."""

from __future__ import annotations

from src.api.schemas.qc_schemas import (
    CODE_CATEGORIES,
)

MAX_QC_ATTEMPTS = 3
MAX_VERIFICATION_PARSE_RETRIES = 1

DEFAULT_INSTRUCTION = (
    "No specific teaching instruction provided. Write for a new IT hire "
    "who knows basic programming but is unfamiliar with the topic."
)

FROZEN_SECTION_CATEGORIES = CODE_CATEGORIES
