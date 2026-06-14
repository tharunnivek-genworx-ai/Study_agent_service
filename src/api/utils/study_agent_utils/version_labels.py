"""Human-readable labels for study material version history."""

from typing import Literal

GenerationType = Literal["generate", "regenerate", "improve", "manual_edit"]

GENERATION_TYPE_LABELS: dict[str, str] = {
    "generate": "Generated",
    "regenerate": "Regenerated",
    "improve": "Improved",
    "manual_edit": "Manual edit",
}


def build_version_display_label(
    version_number: int,
    generation_type: GenerationType | str,
) -> str:
    """Return a mentor-friendly label such as 'v2 (Improved)'."""
    label = GENERATION_TYPE_LABELS.get(
        generation_type,
        str(generation_type).replace("_", " ").title(),
    )
    return f"v{version_number} ({label})"


def truncate_feedback(feedback: str | None, max_length: int = 120) -> str | None:
    if not feedback:
        return None
    text = feedback.strip()
    if len(text) <= max_length:
        return text
    return text[: max_length - 1].rstrip() + "…"
