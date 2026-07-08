"""Topic-scoped artifact directories and filenames for study-agent outputs."""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from uuid import UUID
from zoneinfo import ZoneInfo

ARTIFACTS_ROOT = Path("/app/uploads/artifacts")
IST = ZoneInfo("Asia/Kolkata")

_GENERATION_TYPE_SLUG = {
    "generate": "generate",
    "regenerate": "regenerate",
    "improve": "improve",
    "manual_edit": "manual_edit",
}

# Ordered agent slugs used in run-scoped artifact filenames.
AGENT_ARTIFACT_SLUGS: dict[str, str] = {
    "concept_checklist": "01_concept_checklist",
    "study_generator": "02_study_generator",
    "qc_deterministic": "03_qc_deterministic",
    "qc_extraction": "03_qc_extraction",  # legacy alias
    "qc_verification": "04_qc_verification",
    "qc_result": "05_qc_result",
}


def slugify_topic(title: str, *, max_length: int = 60) -> str:
    """Filesystem-safe slug from a topic title."""
    slug = re.sub(r"[^\w\s-]", "", title.strip(), flags=re.UNICODE)
    slug = re.sub(r"[\s_-]+", "_", slug).strip("_")
    if not slug:
        slug = "topic"
    return slug[:max_length]


def ist_timestamp() -> str:
    """Compact IST timestamp for folder and file names."""
    return datetime.now(IST).strftime("%Y%m%d_%H%M%S")


def topic_dir(topic_title: str, suffix: str) -> Path:
    """e.g. uploads/artifacts/Software_Engineering_SMG/"""
    return ARTIFACTS_ROOT / f"{slugify_topic(topic_title)}_{suffix}"


def run_artifact_dir(topic_title: str, run_id: str) -> Path:
    """e.g. uploads/artifacts/OOPS_SMG/run_20260623_232737/"""
    return topic_dir(topic_title, "SMG") / f"run_{run_id}"


def pipeline_attempt_dir(topic_title: str, run_id: str, pipeline_attempt: int) -> Path:
    """e.g. uploads/artifacts/OOPS_SMG/run_20260623_232737/attempt01/"""
    return run_artifact_dir(topic_title, run_id) / f"attempt{pipeline_attempt:02d}"


def agent_artifact_path(
    topic_title: str,
    run_id: str,
    agent: str,
    *,
    pipeline_attempt: int | None = None,
) -> Path:
    """Per-agent JSON path under a run folder.

    concept_checklist lives at run root; generator/QC agents live under attemptNN/.
    Example: .../OOPS_SMG/run_20260623_232737/attempt01/03_qc_extraction.json
    """
    slug = AGENT_ARTIFACT_SLUGS.get(agent, agent)
    filename = f"{slug}.json"
    base = run_artifact_dir(topic_title, run_id)
    if agent == "concept_checklist":
        return base / filename
    attempt = pipeline_attempt or 1
    return pipeline_attempt_dir(topic_title, run_id, attempt) / filename


def study_material_log_path(
    topic_title: str,
    version_number: int,
    generation_type: str,
    *,
    stamp: str | None = None,
) -> Path:
    """e.g. .../Software_Engineering_SMG/v2_improve_study_material_20260612_170530.json"""
    gen_slug = _GENERATION_TYPE_SLUG.get(generation_type, generation_type)
    ts = stamp or ist_timestamp()
    filename = f"v{version_number}_{gen_slug}_study_material_{ts}.json"
    return topic_dir(topic_title, "SMG") / filename


def llamaparse_log_path(
    topic_title: str,
    material_id: UUID,
    material_label: str,
    label: str,
    *,
    stamp: str | None = None,
) -> Path:
    """e.g. .../Topic_LlamaParse/{uuid}_{name}_20260612_170530_raw.json"""
    ts = stamp or ist_timestamp()
    safe_label = (
        re.sub(r"[^\w\s-]", "", material_label.strip())[:40].strip() or "reference"
    )
    safe_label = re.sub(r"[\s_-]+", "_", safe_label)
    filename = f"{material_id}_{safe_label}_{ts}_{label}.json"
    return topic_dir(topic_title, "LlamaParse") / filename


def reference_llamaparse_images_dir(
    reference_material_id: UUID,
    node_id: UUID,
    *,
    stamp: str | None = None,
) -> Path:
    """e.g. .../reference_llamaparse/{material_id}/{node_id}/images_20260618_120000/"""
    ts = stamp or ist_timestamp()
    return (
        ARTIFACTS_ROOT
        / "reference_llamaparse"
        / str(reference_material_id)
        / str(node_id)
        / f"images_{ts}"
    )


def reference_llamaparse_images_key(
    reference_material_id: UUID,
    node_id: UUID,
    *,
    stamp: str | None = None,
    filename: str,
    gcs_prefix: str = "studyguru/tharun",
) -> str:
    """GCS object key for a LlamaParse figure image."""
    ts = stamp or ist_timestamp()
    safe_name = re.sub(r"[^\w.\-]", "_", Path(filename).name) or "image"
    prefix = gcs_prefix.strip("/")
    return (
        f"{prefix}/reference_llamaparse/"
        f"{reference_material_id}/{node_id}/images_{ts}/{safe_name}"
    )


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path
