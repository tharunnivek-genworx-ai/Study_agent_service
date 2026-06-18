"""Reading-time estimation for study material previews."""

from src.api.utils.trainee_study_utils.content_preview import strip_to_plain_text

# Average adult reading speed used for the "N min read" footer label.
_WORDS_PER_MINUTE = 200


def estimate_read_time_minutes(content: str) -> int:
    """Estimate minutes to read *content* at ~200 wpm (minimum 1).

    Shown in the material preview card footer; not used for progress tracking.
    """
    plain = strip_to_plain_text(content)
    words = [w for w in plain.split() if w]
    if not words:
        return 1
    return max(1, round(len(words) / _WORDS_PER_MINUTE))
