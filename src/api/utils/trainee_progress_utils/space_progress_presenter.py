"""Presentation helpers for trainee space-progress responses."""


def to_score_percentage(score_avg: float | None) -> int | None:
    """Convert normalized score (0..1) to integer percent (0..100)."""
    if score_avg is None:
        return None
    pct = round(score_avg * 100)
    if pct < 0:
        return 0
    if pct > 100:
        return 100
    return pct
