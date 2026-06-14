"""LlamaParse structured extraction for reference materials (Study Agent MVP)."""

from __future__ import annotations

import json
import logging
import re
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID

from llama_cloud import LlamaCloud

from src.api.control.prompts.study_agent_prompts.llama_parse_prompt import (
    LLAMAPARSE_PARSING_INSTRUCTION,
)
from src.api.utils.study_agent_utils.artifact_paths import (
    ensure_dir,
    llamaparse_log_path,
)

logger = logging.getLogger(__name__)

_SCHEMA_PATH = (
    Path(__file__).resolve().parents[2]
    / "schemas"
    / "study_material_schemas"
    / "llama_parse_schema.py"
)

_PAGE_FILENAME_RE = re.compile(
    r"page_(\d+)_(?:chart|image)_(\d+)",
    re.IGNORECASE,
)


@dataclass
class ParseImageRecord:
    """A downloaded figure from the LlamaParse Parse job."""

    parse_index: int
    page_number: int
    figure_index_on_page: int
    filename: str
    path: str
    category: str | None = None
    bbox_y: float = 0.0


def load_study_material_schema() -> dict[str, Any]:
    parsed: dict[str, Any] = json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))
    return parsed


def _save_llamaparse_artifact(
    data: dict[str, Any],
    *,
    topic_title: str,
    material_id: UUID,
    material_label: str,
    label: str,
    stamp: str,
) -> None:
    """Persist LlamaParse JSON under {topic}_LlamaParse/."""
    try:
        out_path = llamaparse_log_path(
            topic_title,
            material_id,
            material_label,
            label,
            stamp=stamp,
        )
        ensure_dir(out_path.parent)
        out_path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        logger.info("LlamaParse artifact saved → %s", out_path)
    except OSError as exc:
        logger.error("Could not save LlamaParse artifact (%s): %s", label, exc)


def _parse_filename_page_meta(filename: str) -> tuple[int | None, int | None]:
    """Extract (page_number, figure_index_on_page) from LlamaParse filenames."""
    match = _PAGE_FILENAME_RE.search(filename)
    if not match:
        return None, None
    return int(match.group(1)), int(match.group(2))


def _normalize_page_number(api_page: int | None, filename: str) -> int:
    """Resolve a 1-based page number, preferring the filename when available."""
    from_filename, _ = _parse_filename_page_meta(filename)
    if from_filename is not None:
        return from_filename
    if api_page is not None:
        return api_page if api_page >= 1 else api_page + 1
    return 1


def _bbox_y(img_meta: Any) -> float:
    bbox = getattr(img_meta, "bbox", None)
    if bbox is None:
        return 0.0
    return float(getattr(bbox, "y", 0) or 0)


def download_figures(
    client: LlamaCloud,
    file_id: str,
    images_dir: Path,
) -> list[ParseImageRecord]:
    """Run a Parse job and download extracted images with original filenames."""
    images_dir.mkdir(parents=True, exist_ok=True)

    parse_job = client.parsing.create(
        file_id=file_id,
        tier="agentic",
        version="latest",
    )
    parse_job_id = parse_job.id

    status: str | None = None
    for _ in range(300):
        parse_job = client.parsing.get(parse_job_id)
        job_obj = getattr(parse_job, "job", None)
        status = (
            getattr(job_obj, "status", None)
            if job_obj is not None
            else getattr(parse_job, "status", None)
        )
        if status in ("SUCCESS", "COMPLETED", "FAILED", "ERROR", "CANCELLED"):
            break
        time.sleep(1)

    if status not in ("SUCCESS", "COMPLETED"):
        return []

    parse_result = client.parsing.get(
        parse_job_id,
        expand=["images_content_metadata"],
    )

    images_meta = parse_result.images_content_metadata
    if not images_meta or not images_meta.images:
        return []

    raw_records: list[ParseImageRecord] = []
    for img_meta in images_meta.images:
        filename = img_meta.filename
        presigned_url = img_meta.presigned_url
        if not presigned_url:
            continue

        try:
            with urllib.request.urlopen(presigned_url) as response:
                binary_data = response.read()
        except OSError:
            continue

        local_path = images_dir / filename
        local_path.write_bytes(binary_data)

        api_page = getattr(img_meta, "page_number", None)
        page_number = _normalize_page_number(api_page, filename)
        _, filename_ordinal = _parse_filename_page_meta(filename)

        raw_records.append(
            ParseImageRecord(
                parse_index=int(getattr(img_meta, "index", len(raw_records))),
                page_number=page_number,
                figure_index_on_page=filename_ordinal or 1,
                filename=filename,
                path=str(local_path),
                category=getattr(img_meta, "category", None),
                bbox_y=_bbox_y(img_meta),
            )
        )

    return _assign_figure_ordinals_on_page(raw_records)


def _assign_figure_ordinals_on_page(
    records: list[ParseImageRecord],
) -> list[ParseImageRecord]:
    """Recompute figure_index_on_page by grouping on page and sorting top-to-bottom."""
    by_page: dict[int, list[ParseImageRecord]] = {}
    for record in records:
        by_page.setdefault(record.page_number, []).append(record)

    for group in by_page.values():
        group.sort(key=lambda item: (item.bbox_y, item.parse_index, item.filename))
        for ordinal, record in enumerate(group, start=1):
            record.figure_index_on_page = ordinal

    records.sort(
        key=lambda item: (item.page_number, item.figure_index_on_page, item.parse_index)
    )
    return records


def _attach_reference_images(
    structured_data: dict[str, Any],
    parse_images: list[ParseImageRecord],
) -> dict[str, Any]:
    """Attach downloaded figure files for the UI reference-images panel.

    Image metadata for generation lives in each section's ``images`` array
    (``full_description``, ``purpose``). Downloaded binaries are listed here
    separately — they are NOT matched or embedded into study material content.
    """
    structured_data["reference_images"] = [
        {
            "filename": record.filename,
            "storage_path": record.path,
            "source_page": record.page_number,
            "figure_index_on_page": record.figure_index_on_page,
            "parse_index": record.parse_index,
            "category": record.category,
        }
        for record in parse_images
    ]
    return structured_data


def extract_structured_reference(
    file_path: str,
    api_key: str,
    *,
    images_dir: str | Path | None = None,
    topic_title: str = "topic",
    reference_material_id: UUID | None = None,
    material_label: str | None = None,
    artifact_stamp: str | None = None,
) -> dict[str, Any]:
    """Upload a PDF, extract structured JSON, and download reference figure files."""
    from src.api.utils.study_agent_utils.artifact_paths import (
        ist_timestamp,
        nodemedia_images_dir,
    )

    source = Path(file_path)
    if not source.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    stamp = artifact_stamp or ist_timestamp()
    resolved_images_dir = (
        Path(images_dir)
        if images_dir
        else nodemedia_images_dir(topic_title, stamp=stamp)
    )
    ensure_dir(resolved_images_dir)

    client = LlamaCloud(api_key=api_key)

    file_obj = client.files.create(file=str(source), purpose="extract")
    file_id = file_obj.id

    job = client.extract.create(
        file_input=file_id,
        configuration={
            "data_schema": load_study_material_schema(),
            "extraction_target": "per_doc",
            "tier": "agentic",
            "system_prompt": LLAMAPARSE_PARSING_INSTRUCTION,
        },
    )

    for _ in range(300):
        if job.status in ("COMPLETED", "FAILED", "CANCELLED"):
            break
        time.sleep(1)
        job = client.extract.get(job.id)

    if job.status != "COMPLETED":
        raise RuntimeError(f"Extraction job ended with status: {job.status}")

    result = job.extract_result
    if isinstance(result, list) and result:
        structured_data = result[0]
    elif isinstance(result, dict):
        structured_data = result
    else:
        raise RuntimeError("No valid result returned from extraction job.")

    mat_id = reference_material_id or UUID("00000000-0000-0000-0000-000000000000")
    mat_label = material_label or source.stem

    _save_llamaparse_artifact(
        structured_data,
        topic_title=topic_title,
        material_id=mat_id,
        material_label=mat_label,
        label="raw",
        stamp=stamp,
    )

    parse_images = download_figures(
        client=client,
        file_id=file_id,
        images_dir=resolved_images_dir,
    )

    enriched = _attach_reference_images(structured_data, parse_images)
    enriched["_images_dir"] = str(resolved_images_dir)
    enriched["_artifact_stamp"] = stamp

    logger.info(
        "LlamaParse extraction complete: %d section image metadata entr(ies), "
        "%d downloaded reference figure(s) → %s",
        sum(
            len(section.get("images") or [])
            for section in enriched.get("sections") or []
        ),
        len(parse_images),
        resolved_images_dir,
    )

    _save_llamaparse_artifact(
        enriched,
        topic_title=topic_title,
        material_id=mat_id,
        material_label=mat_label,
        label="enriched",
        stamp=stamp,
    )

    return enriched
