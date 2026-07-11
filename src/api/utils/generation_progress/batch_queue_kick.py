"""Server-side sequential generate-all driver.

Each kick must run inside an active HTTP request on Cloud Run (CPU freezes after
the response). Callers should ``await kick_space_queue(...)`` before returning,
and GET batch detail should re-arm kicks for stalled queues.
"""

from __future__ import annotations

import asyncio
import logging
import time
from uuid import UUID

from src.api.data.clients.postgres.database import SessionLocal
from src.api.utils.generation_progress.advisory_lock import release_all_generation_locks
from src.api.utils.generation_progress.generation_job_executor import (
    run_generation_job,
)

logger = logging.getLogger(__name__)

_kick_inflight: set[str] = set()
_kick_last_at: dict[str, float] = {}
_KICK_DEBOUNCE_SECONDS = 0.5
_kick_guard = asyncio.Lock()
# Claim/start at most one queued item per kick, but await that generation inline
# (Cloud Run keeps CPU for the graph). Callers re-invoke kick for the next node.
_MAX_CLAIM_ATTEMPTS = 8


async def kick_space_queue(
    *,
    space_id: UUID,
    mentor_id: UUID,
    role: str = "mentor",
    force: bool = False,
) -> dict:
    """Start the next queued node via the normal study-material generate path.

    Returns a small status dict for debug/logging. Safe to call from HTTP handlers.
    """
    from src.api.core.services.study_agent_services.study_material_batch_service import (
        StudyMaterialBatchService,
    )
    from src.api.core.services.study_agent_services.study_material_service import (
        StudyMaterialService,
    )

    space_key = str(space_id)
    async with _kick_guard:
        if space_key in _kick_inflight:
            return {
                "ok": False,
                "reason": "kick_already_inflight",
                "space_id": space_key,
            }
        now = time.monotonic()
        if (
            not force
            and now - _kick_last_at.get(space_key, 0.0) < _KICK_DEBOUNCE_SECONDS
        ):
            return {"ok": False, "reason": "kick_debounced", "space_id": space_key}
        _kick_inflight.add(space_key)
        _kick_last_at[space_key] = now

    try:
        for attempt in range(_MAX_CLAIM_ATTEMPTS):
            async with SessionLocal() as session:
                try:
                    service = StudyMaterialBatchService(session)
                    result = await service.advance_space_queue(
                        space_id=space_id,
                        mentor_id=mentor_id,
                        role=role,
                    )
                    await session.commit()

                    if result.scheduled_run_id is not None:
                        run_id = result.scheduled_run_id
                        logger.info(
                            "Generate-all inline run starting",
                            extra={
                                "space_id": space_key,
                                "run_id": str(run_id),
                                "attempt": attempt,
                            },
                        )
                        await run_generation_job(
                            lambda sess, rid=run_id, uid=mentor_id: (
                                StudyMaterialService(
                                    sess
                                ).execute_generate_study_material(
                                    run_id=rid, user_id=uid
                                )
                            ),
                        )
                        async with SessionLocal() as after_session:
                            snapshot = await StudyMaterialBatchService(
                                after_session
                            ).get_space_queue(
                                space_id=space_id,
                                mentor_id=mentor_id,
                                role=role,
                            )
                            await after_session.commit()
                        logger.info(
                            "Generate-all inline run finished",
                            extra={
                                "space_id": space_key,
                                "run_id": str(run_id),
                                "needs_advance": snapshot.needs_advance,
                            },
                        )
                        return {
                            "ok": True,
                            "reason": "completed_inline_node",
                            "space_id": space_key,
                            "run_id": str(run_id),
                            "needs_advance": snapshot.needs_advance,
                            "current_item_id": (
                                str(snapshot.current_item.item_id)
                                if snapshot.current_item
                                else None
                            ),
                            "current_node_id": (
                                str(snapshot.current_item.node_id)
                                if snapshot.current_item
                                else None
                            ),
                        }

                    if result.snapshot.advance_deferred:
                        return {
                            "ok": False,
                            "reason": "advance_deferred",
                            "space_id": space_key,
                            "needs_advance": result.snapshot.needs_advance,
                        }

                    if not result.snapshot.needs_advance:
                        return {
                            "ok": True,
                            "reason": "idle_or_waiting_on_running_item",
                            "space_id": space_key,
                            "needs_advance": False,
                            "current_item_id": (
                                str(result.snapshot.current_item.item_id)
                                if result.snapshot.current_item
                                else None
                            ),
                        }

                    # Skipped/failed on start — try next item quickly.
                    continue
                except Exception:
                    await session.rollback()
                    logger.exception(
                        "Generate-all kick attempt failed",
                        extra={"space_id": space_key, "attempt": attempt},
                    )
                    return {
                        "ok": False,
                        "reason": "kick_exception",
                        "space_id": space_key,
                        "attempt": attempt,
                    }
                finally:
                    await release_all_generation_locks(session)

        return {"ok": False, "reason": "claim_exhausted", "space_id": space_key}
    finally:
        async with _kick_guard:
            _kick_inflight.discard(space_key)


def schedule_space_queue_kick(
    *,
    space_id: UUID,
    mentor_id: UUID,
    role: str = "mentor",
    force: bool = False,
) -> None:
    """Fire-and-forget wrapper — prefer ``await kick_space_queue`` on Cloud Run."""

    async def _wrapper() -> None:
        try:
            await kick_space_queue(
                space_id=space_id,
                mentor_id=mentor_id,
                role=role,
                force=force,
            )
        except Exception:
            logger.exception(
                "Generate-all scheduled kick failed",
                extra={"space_id": str(space_id)},
            )

    asyncio.create_task(_wrapper())
