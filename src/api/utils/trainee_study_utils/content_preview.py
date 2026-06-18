"""Plain-text preview helpers for study material content.

The detail panel shows a short snippet (not the full markdown body). These
helpers strip formatting noise so previews read cleanly in the UI.
"""

import re

# Patterns removed before preview extraction (images, links, headings, emphasis).
_MARKDOWN_NOISE = re.compile(
    r"!\[[^\]]*\]\([^)]+\)|\[[^\]]+\]\([^)]+\)|#{1,6}\s+|`{1,3}|>{1,}\s?|\*{1,2}|_{1,2}",
)
_HTML_TAG = re.compile(r"<[^>]+>")


def strip_to_plain_text(content: str) -> str:
    """Remove common markdown/html markers and collapse whitespace.

    Used by both ``build_content_preview`` and ``estimate_read_time_minutes``
    so preview text and read-time use the same word count basis.
    """
    text = _HTML_TAG.sub(" ", content or "")
    text = _MARKDOWN_NOISE.sub(" ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def build_content_preview(content: str, *, max_chars: int = 280) -> str:
    """Return the first few sentences of readable preview text.

    Caps at roughly three sentences or *max_chars* — whichever comes first —
    so the material preview card stays compact in the detail panel.
    """
    plain = strip_to_plain_text(content)
    if not plain:
        return ""

    sentences = re.split(r"(?<=[.!?])\s+", plain)
    preview_parts: list[str] = []
    total = 0
    for sentence in sentences:
        chunk = sentence.strip()
        if not chunk:
            continue
        if total + len(chunk) > max_chars and preview_parts:
            break
        preview_parts.append(chunk)
        total += len(chunk) + 1
        if len(preview_parts) >= 3:
            break

    if preview_parts:
        return " ".join(preview_parts)

    return plain[:max_chars].rstrip() + ("…" if len(plain) > max_chars else "")
