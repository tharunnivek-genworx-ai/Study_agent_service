"""Format LlamaParse structured output into LLM-ready reference text."""

from typing import Any

# Diagram-as-code is excluded from LLM text — image Description/Purpose fields are authoritative.
_DIAGRAM_CODE_LANGUAGES = frozenset(
    {"mermaid", "flowchart", "graphviz", "dot", "plantuml", "graph"}
)


def _is_diagram_code_block(language: str, code: str) -> bool:
    lang = (language or "").strip().lower()
    if lang in _DIAGRAM_CODE_LANGUAGES:
        return True
    head = (code or "")[:300].lower()
    return (
        "graph td" in head
        or "graph lr" in head
        or head.lstrip().startswith("flowchart ")
    )


def _iter_section_images(
    structured_data: dict[str, Any],
) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    pairs: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for section in structured_data.get("sections") or []:
        for image in section.get("images") or []:
            pairs.append((section, image))
    return pairs


def format_parsed_reference(structured_data: dict[str, Any]) -> str:
    """Convert structured LlamaParse output to text for the study agent."""
    parts: list[str] = []

    meta = structured_data.get("document_metadata") or {}
    title = meta.get("detected_title")
    if title:
        parts.append(f"Document: {title}")

    topics = meta.get("detected_topics") or []
    if topics:
        parts.append("Topics: " + ", ".join(topics))

    unsectioned = structured_data.get("unsectioned_content")
    if unsectioned:
        parts.append(str(unsectioned))

    for section in structured_data.get("sections") or []:
        heading = section.get("heading", "")
        body = section.get("body_text", "")
        if heading or body:
            parts.append(f"{heading}\n{body}".strip())

        for block in section.get("code_blocks") or []:
            language = block.get("language") or ""
            code = block.get("code") or ""
            if _is_diagram_code_block(language, code):
                continue
            caption = block.get("caption")
            if caption:
                parts.append(str(caption))
            parts.append(f"```{language}\n{code}\n```")

        for image in section.get("images") or []:
            figure_label = image.get("figure_label") or image.get("semantic_name") or ""
            section_label = (
                heading.strip() or f"section {section.get('section_index', '')}"
            )
            parts.append(
                f"[IMAGE: {figure_label}]\n"
                f"Reference section: {section_label}\n"
                f"Type: {image.get('image_type', 'other')}\n"
                f"Description: {image.get('full_description', '')}\n"
                f"Purpose: {image.get('purpose', '')}"
            )

        for table in section.get("tables") or []:
            caption = table.get("caption")
            if caption:
                parts.append(str(caption))
            markdown_table = table.get("markdown_table")
            if markdown_table:
                parts.append(str(markdown_table))

    image_pairs = _iter_section_images(structured_data)
    if image_pairs:
        inventory_lines = [
            "The following diagrams were extracted from the reference. "
            "Each MUST receive detailed coverage in Section 3 (How It Works) — "
            "expand on its Description using the section body text. Do not skip any entry.",
            "",
        ]
        for index, (section, image) in enumerate(image_pairs, start=1):
            heading = (section.get("heading") or "").strip()
            label = (
                image.get("figure_label")
                or image.get("semantic_name")
                or f"diagram_{index}"
            )
            inventory_lines.append(
                f"{index}. {label} — section: {heading or '(no heading)'}"
            )
        parts.append("## DIAGRAMS TO COVER IN SECTION 3\n" + "\n".join(inventory_lines))

    notes = structured_data.get("extraction_notes") or []
    if notes:
        parts.append("Extraction notes:\n" + "\n".join(f"- {note}" for note in notes))

    return "\n\n".join(part for part in parts if part.strip())
