"""Fire-and-forget progress updates at node entry (visible to pollers)."""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from langchain_core.runnables import RunnableConfig

from src.api.data.clients.postgres.database import SessionLocal
from src.api.schemas import GenerationPipeline
from src.api.utils.generation_progress.db_store import DbGenerationProgressStore

logger = logging.getLogger(__name__)


def run_id_from_config(config: RunnableConfig | dict[str, Any] | None) -> UUID | None:
    if not config:
        return None
    configurable = config.get("configurable", {}) if isinstance(config, dict) else {}
    raw = configurable.get("run_id")
    if raw is None:
        return None
    if isinstance(raw, UUID):
        return raw
    try:
        return UUID(str(raw))
    except (TypeError, ValueError):
        return None


def pipeline_from_config(
    config: RunnableConfig | dict[str, Any] | None,
    *,
    default: GenerationPipeline,
) -> GenerationPipeline:
    if not config:
        return default
    configurable = config.get("configurable", {}) if isinstance(config, dict) else {}
    raw = configurable.get("pipeline")
    if raw is None:
        return default
    try:
        return GenerationPipeline(str(raw))
    except ValueError:
        return default


async def report_node_enter(
    run_id: UUID,
    pipeline: GenerationPipeline,
    node_name: str,
) -> None:
    """Update progress step when a graph node starts (commits in its own session)."""
    try:
        async with SessionLocal() as session:
            store = DbGenerationProgressStore(session)
            await store.on_node(run_id, pipeline, node_name)
    except Exception:
        logger.exception(
            "Failed to report node-enter progress for run=%s node=%s",
            run_id,
            node_name,
        )


async def maybe_report_node_enter(
    config: RunnableConfig | dict[str, Any] | None,
    node_name: str,
    *,
    default_pipeline: GenerationPipeline,
) -> None:
    run_id = run_id_from_config(config)
    if run_id is None:
        return
    pipeline = pipeline_from_config(config, default=default_pipeline)
    await report_node_enter(run_id, pipeline, node_name)
