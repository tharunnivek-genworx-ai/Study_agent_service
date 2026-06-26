"""Convert study material Markdown to a styled PDF byte stream (ReportLab — no native deps)."""

from __future__ import annotations

import re
from collections.abc import Iterator
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, Preformatted, SimpleDocTemplate, Spacer


def _sanitize_filename(title: str) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*]+', "", title).strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned or "study-material"


def build_study_material_pdf_filename(node_title: str) -> str:
    return f"{_sanitize_filename(node_title)}.pdf"


def _escape_xml(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _inline_markdown_to_reportlab(text: str) -> str:
    """Convert a subset of inline Markdown to ReportLab paragraph markup."""
    escaped = _escape_xml(text)
    escaped = re.sub(r"`([^`]+)`", r'<font face="Courier" size="9">\1</font>', escaped)
    escaped = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", escaped)
    escaped = re.sub(r"\*([^*]+)\*", r"<i>\1</i>", escaped)
    escaped = re.sub(r"_([^_]+)_", r"<i>\1</i>", escaped)
    return escaped


def _iter_markdown_blocks(markdown_content: str) -> Iterator[tuple[str, str]]:
    """Yield (block_type, content) tuples from Markdown source."""
    lines = markdown_content.replace("\r\n", "\n").split("\n")
    index = 0
    while index < len(lines):
        line = lines[index]
        stripped = line.strip()

        if not stripped:
            index += 1
            continue

        if stripped.startswith("```"):
            fence = stripped[:3]
            code_lines: list[str] = []
            index += 1
            while index < len(lines) and not lines[index].strip().startswith(fence):
                code_lines.append(lines[index])
                index += 1
            if index < len(lines):
                index += 1
            yield ("code", "\n".join(code_lines))
            continue

        heading_match = re.match(r"^(#{1,3})\s+(.+)$", stripped)
        if heading_match:
            level = len(heading_match.group(1))
            yield (f"h{level}", heading_match.group(2).strip())
            index += 1
            continue

        if re.match(r"^>\s?", stripped):
            quote_lines: list[str] = []
            while index < len(lines):
                current = lines[index].strip()
                if not current.startswith(">"):
                    break
                quote_lines.append(re.sub(r"^>\s?", "", current))
                index += 1
            yield ("quote", " ".join(quote_lines))
            continue

        if re.match(r"^[-*+]\s+", stripped):
            items: list[str] = []
            while index < len(lines):
                current = lines[index].strip()
                bullet_match = re.match(r"^[-*+]\s+(.+)$", current)
                if not bullet_match:
                    break
                items.append(bullet_match.group(1))
                index += 1
            yield ("ul", "\n".join(items))
            continue

        if re.match(r"^\d+\.\s+", stripped):
            items = []
            while index < len(lines):
                current = lines[index].strip()
                ordered_match = re.match(r"^\d+\.\s+(.+)$", current)
                if not ordered_match:
                    break
                items.append(ordered_match.group(1))
                index += 1
            yield ("ol", "\n".join(items))
            continue

        paragraph_lines: list[str] = [stripped]
        index += 1
        while (
            index < len(lines)
            and lines[index].strip()
            and not lines[index].startswith(("#", ">", "-", "*", "+", "```"))
            and not re.match(r"^\d+\.\s+", lines[index].strip())
        ):
            paragraph_lines.append(lines[index].strip())
            index += 1
        yield ("p", " ".join(paragraph_lines))


def _build_styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "StudyMaterialTitle",
            parent=base["Title"],
            fontSize=20,
            leading=24,
            textColor=colors.HexColor("#0f172a"),
            spaceAfter=6,
        ),
        "subtitle": ParagraphStyle(
            "StudyMaterialSubtitle",
            parent=base["Normal"],
            fontSize=9,
            leading=12,
            textColor=colors.HexColor("#64748b"),
            spaceAfter=14,
        ),
        "h1": ParagraphStyle(
            "StudyMaterialH1",
            parent=base["Heading1"],
            fontSize=18,
            leading=22,
            textColor=colors.HexColor("#0f172a"),
            spaceBefore=12,
            spaceAfter=8,
        ),
        "h2": ParagraphStyle(
            "StudyMaterialH2",
            parent=base["Heading2"],
            fontSize=15,
            leading=19,
            textColor=colors.HexColor("#0f172a"),
            spaceBefore=10,
            spaceAfter=6,
        ),
        "h3": ParagraphStyle(
            "StudyMaterialH3",
            parent=base["Heading3"],
            fontSize=13,
            leading=17,
            textColor=colors.HexColor("#0f172a"),
            spaceBefore=8,
            spaceAfter=4,
        ),
        "body": ParagraphStyle(
            "StudyMaterialBody",
            parent=base["BodyText"],
            fontSize=11,
            leading=16,
            textColor=colors.HexColor("#1e293b"),
            alignment=TA_LEFT,
            spaceAfter=8,
        ),
        "quote": ParagraphStyle(
            "StudyMaterialQuote",
            parent=base["BodyText"],
            fontSize=11,
            leading=16,
            textColor=colors.HexColor("#475569"),
            leftIndent=12,
            borderPadding=4,
            spaceAfter=8,
        ),
        "list": ParagraphStyle(
            "StudyMaterialList",
            parent=base["BodyText"],
            fontSize=11,
            leading=16,
            textColor=colors.HexColor("#1e293b"),
            leftIndent=14,
            spaceAfter=4,
        ),
    }


def render_study_material_pdf(title: str, markdown_content: str) -> bytes:
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=2 * cm,
        rightMargin=2 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
        title=_sanitize_filename(title),
    )
    styles = _build_styles()
    story: list[object] = [
        Paragraph(_escape_xml(title), styles["title"]),
        Paragraph("StudyGuru · Study Material", styles["subtitle"]),
        Spacer(1, 6),
    ]

    for block_type, content in _iter_markdown_blocks(markdown_content):
        if block_type == "code":
            story.append(
                Preformatted(
                    content or " ",
                    styles["body"],
                    maxLineLength=96,
                )
            )
            story.append(Spacer(1, 6))
            continue

        if block_type in {"h1", "h2", "h3"}:
            story.append(
                Paragraph(_inline_markdown_to_reportlab(content), styles[block_type])
            )
            continue

        if block_type == "quote":
            story.append(
                Paragraph(_inline_markdown_to_reportlab(content), styles["quote"])
            )
            continue

        if block_type in {"ul", "ol"}:
            prefix = "•" if block_type == "ul" else "%d."
            for idx, item in enumerate(content.split("\n"), start=1):
                bullet = prefix if block_type == "ul" else f"{idx}."
                story.append(
                    Paragraph(
                        f"{bullet} {_inline_markdown_to_reportlab(item)}",
                        styles["list"],
                    )
                )
            story.append(Spacer(1, 4))
            continue

        story.append(Paragraph(_inline_markdown_to_reportlab(content), styles["body"]))

    doc.build(story)
    return buffer.getvalue()
