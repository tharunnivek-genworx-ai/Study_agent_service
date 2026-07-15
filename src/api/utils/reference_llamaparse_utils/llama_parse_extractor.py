"""LlamaParse structured extraction for reference materials (Study Agent MVP)."""

from __future__ import annotations

import hashlib
import json
import logging
import mimetypes
import re
import time
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Any
from uuid import UUID

from llama_cloud import LlamaCloud

from src.api.config import feature_settings, settings
from src.api.control.study_agent.prompts.parsing import build_parsing_instruction
from src.api.core.exceptions import GenerationRunAborted
from src.api.schemas.study_material_schemas.llama_parse_schema import (
    LlamaParseExtractionResult,
    ParseImageRecord,
    load_study_material_schema,
)
from src.api.utils.storage.object_storage import (
    build_llamaparse_image_key,
    upload_bytes_sync,
)
from src.api.utils.study_agent_utils.artifacts.artifact_paths import (
    ensure_dir,
    ist_timestamp,
    llamaparse_log_path,
    reference_llamaparse_images_dir,
)

logger = logging.getLogger(__name__)

_PAGE_FILENAME_RE = re.compile(
    r"page_(\d+)_(?:chart|image)_(\d+)",
    re.IGNORECASE,
)

JobIdsCallback = Callable[[str | None, str | None], None]
ShouldContinue = Callable[[], bool]


def _abort_if_should_stop(should_continue: ShouldContinue | None) -> None:
    if should_continue is not None and not should_continue():
        raise GenerationRunAborted()


def compute_pdf_content_hash(file_path: str | Path) -> str:
    """SHA-256 digest of PDF bytes — reserved for cross-upload deduplication."""
    source = Path(file_path)
    return hashlib.sha256(source.read_bytes()).hexdigest()


def _save_llamaparse_artifact(
    data: dict[str, Any],
    *,
    topic_title: str,
    material_id: UUID,
    material_label: str,
    label: str,
    stamp: str,
) -> None:
    """Persist LlamaParse JSON under {topic}_LlamaParse/ for debug logging only."""
    if not feature_settings.enable_artifact_logging:
        return
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
    *,
    reference_material_id: UUID,
    node_id: UUID,
    stamp: str,
    images_dir: Path | None = None,
    should_continue: ShouldContinue | None = None,
    on_job_ids: JobIdsCallback | None = None,
    extract_job_id: str | None = None,
) -> tuple[list[ParseImageRecord], str | None]:
    """Run a Parse job and download extracted images with original filenames."""
    use_gcs = settings.storage_backend == "gcs"
    if not use_gcs and images_dir is not None:
        images_dir.mkdir(parents=True, exist_ok=True)

    _abort_if_should_stop(should_continue)
    parse_job_create = client.parsing.create(
        file_id=file_id,
        tier="agentic",
        version="latest",
    )
    parse_job_id = parse_job_create.id
    if on_job_ids is not None:
        on_job_ids(extract_job_id, parse_job_id)

    status: str | None = None
    for _ in range(300):
        _abort_if_should_stop(should_continue)
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
        return [], parse_job_id

    parse_result = client.parsing.get(
        parse_job_id,
        expand=["images_content_metadata"],
    )

    images_meta = parse_result.images_content_metadata
    if not images_meta or not images_meta.images:
        return [], parse_job_id

    raw_records: list[ParseImageRecord] = []
    for img_meta in images_meta.images:
        _abort_if_should_stop(should_continue)
        filename = img_meta.filename
        presigned_url = img_meta.presigned_url
        if not presigned_url:
            continue

        try:
            with urllib.request.urlopen(presigned_url) as response:
                binary_data = response.read()
        except OSError:
            continue

        _abort_if_should_stop(should_continue)
        content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
        if use_gcs:
            object_key = build_llamaparse_image_key(
                reference_material_id, node_id, stamp, filename
            )
            storage_ref = upload_bytes_sync(object_key, binary_data, content_type)
        else:
            assert images_dir is not None
            local_path = images_dir / filename
            local_path.write_bytes(binary_data)
            storage_ref = str(local_path)

        api_page = getattr(img_meta, "page_number", None)
        page_number = _normalize_page_number(api_page, filename)
        _, filename_ordinal = _parse_filename_page_meta(filename)

        raw_records.append(
            ParseImageRecord(
                parse_index=int(getattr(img_meta, "index", len(raw_records))),
                page_number=page_number,
                figure_index_on_page=filename_ordinal or 1,
                filename=filename,
                path=storage_ref,
                category=getattr(img_meta, "category", None),
                bbox_y=_bbox_y(img_meta),
            )
        )

    return _assign_figure_ordinals_on_page(raw_records), parse_job_id


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


def _parse_extract_result(result: Any) -> dict[str, Any]:
    """Normalize LlamaCloud extract job payload to a structured dict."""
    if isinstance(result, list) and result:
        structured_data = result[0]
    elif isinstance(result, dict):
        structured_data = result
    else:
        raise RuntimeError("No valid result returned from extraction job.")
    if not isinstance(structured_data, dict):
        raise RuntimeError("Extraction job result is not a JSON object.")
    return structured_data


def fetch_structured_data_from_extract_job(
    api_key: str,
    extract_job_id: str,
) -> dict[str, Any]:
    """Retrieve structured JSON for a completed LlamaCloud extract job by id."""
    client = LlamaCloud(api_key=api_key)
    job = client.extract.get(extract_job_id)
    status = getattr(job, "status", None)
    if status != "COMPLETED":
        raise RuntimeError(
            f"Cannot reuse extract job {extract_job_id}: status is {status!r}."
        )
    return _parse_extract_result(job.extract_result)


def extract_structured_reference(
    file_path: str,
    api_key: str,
    *,
    node_id: UUID,
    images_dir: str | Path | None = None,
    topic_title: str = "topic",
    reference_material_id: UUID | None = None,
    material_label: str | None = None,
    artifact_stamp: str | None = None,
    should_continue: ShouldContinue | None = None,
    on_job_ids: JobIdsCallback | None = None,
) -> LlamaParseExtractionResult:
    """Upload a PDF, extract structured JSON, and download reference figure files."""
    source = Path(file_path)
    if not source.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    if reference_material_id is None:
        raise ValueError("reference_material_id is required for LlamaParse extraction.")

    stamp = artifact_stamp or ist_timestamp()
    content_hash = compute_pdf_content_hash(source)
    resolved_images_dir: Path | None = None
    if settings.storage_backend != "gcs":
        resolved_images_dir = (
            Path(images_dir)
            if images_dir
            else reference_llamaparse_images_dir(
                reference_material_id, node_id, stamp=stamp
            )
        )
        ensure_dir(resolved_images_dir)

    client = LlamaCloud(api_key=api_key)

    _abort_if_should_stop(should_continue)
    file_obj = client.files.create(file=str(source), purpose="extract")
    file_id = file_obj.id

    parsing_instruction = build_parsing_instruction()

    _abort_if_should_stop(should_continue)
    job = client.extract.create(
        file_input=file_id,
        configuration={
            "data_schema": load_study_material_schema(),
            "extraction_target": "per_doc",
            "tier": "agentic",
            "system_prompt": parsing_instruction,
        },
    )
    extract_job_id = job.id
    if on_job_ids is not None:
        on_job_ids(extract_job_id, None)

    for _ in range(300):
        _abort_if_should_stop(should_continue)
        if job.status in ("COMPLETED", "FAILED", "CANCELLED"):
            break
        time.sleep(1)
        job = client.extract.get(job.id)

    if job.status != "COMPLETED":
        raise RuntimeError(f"Extraction job ended with status: {job.status}")

    structured_data = _parse_extract_result(job.extract_result)

    mat_label = material_label or source.stem

    _save_llamaparse_artifact(
        structured_data,
        topic_title=topic_title,
        material_id=reference_material_id,
        material_label=mat_label,
        label="raw",
        stamp=stamp,
    )

    parse_images, parse_job_id = download_figures(
        client=client,
        file_id=file_id,
        reference_material_id=reference_material_id,
        node_id=node_id,
        stamp=stamp,
        images_dir=resolved_images_dir,
        should_continue=should_continue,
        on_job_ids=on_job_ids,
        extract_job_id=extract_job_id,
    )

    logger.info(
        "LlamaParse extraction complete: %d section image metadata entr(ies), "
        "%d downloaded reference figure(s)",
        sum(
            len(section.get("images") or [])
            for section in structured_data.get("sections") or []
        ),
        len(parse_images),
    )

    return LlamaParseExtractionResult(
        structured_data=structured_data,
        extract_job_id=extract_job_id,
        parse_job_id=parse_job_id,
        content_hash=content_hash,
        parse_images=parse_images,
    )
