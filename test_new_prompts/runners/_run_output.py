"""Write structured run artifacts under test_new_prompts/run_output."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from test_new_prompts.runners._paths import RUN_OUTPUT_DIR


def slugify_topic(topic: str, *, max_length: int = 60) -> str:
    slug = re.sub(r"[^\w\s-]", "", topic.strip().lower())
    slug = re.sub(r"[\s_-]+", "_", slug).strip("_")
    if not slug:
        slug = "untitled_topic"
    return slug[:max_length]


def timestamp_stamp(when: datetime | None = None) -> str:
    moment = when or datetime.now(UTC)
    return moment.strftime("%Y%m%d_%H%M%S")


def create_run_dir(topic: str, when: datetime | None = None) -> tuple[Path, str, str]:
    """Return (run_dir, topic_slug, timestamp) for a new test run."""
    moment = when or datetime.now(UTC)
    topic_slug = slugify_topic(topic)
    stamp = timestamp_stamp(moment)
    run_dir = RUN_OUTPUT_DIR / f"{topic_slug}_{stamp}"
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir, topic_slug, stamp


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )


def write_run_manifest(
    run_dir: Path,
    *,
    topic: str,
    topic_slug: str,
    timestamp: str,
    started_at: datetime,
    finished_at: datetime,
    generation_dir: Path,
    qc_dir: Path | None = None,
    extra: dict[str, Any] | None = None,
) -> Path:
    manifest = {
        "topic": topic,
        "topic_slug": topic_slug,
        "timestamp": timestamp,
        "started_at": started_at.isoformat(),
        "finished_at": finished_at.isoformat(),
        "generation_output_dir": str(generation_dir),
        "qc_output_dir": str(qc_dir) if qc_dir else None,
    }
    if extra:
        manifest.update(extra)
    manifest_path = run_dir / "run_manifest.json"
    write_json(manifest_path, manifest)
    return manifest_path
