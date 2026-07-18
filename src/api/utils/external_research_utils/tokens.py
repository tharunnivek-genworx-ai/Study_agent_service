"""Shared token-count helpers for external research pipeline floors."""

from __future__ import annotations


def rough_token_count(text: str) -> int:
    """Cheap approximation: ~1.3 tokens per whitespace-separated word."""
    if not text or not text.strip():
        return 0
    return int(len(text.split()) * 1.3)
