"""Procrastinate application for durable generate-all batch processing."""

from __future__ import annotations

import contextlib
from collections.abc import AsyncIterator

import procrastinate
from procrastinate.exceptions import AppNotOpen

from src.api.config.dbconfig import build_procrastinate_conninfo

app = procrastinate.App(
    connector=procrastinate.PsycopgConnector(
        conninfo=build_procrastinate_conninfo(),
    ),
)


def _pool_is_open() -> bool:
    connector = app.connector
    try:
        return getattr(connector, "pool", None) is not None
    except (AppNotOpen, AttributeError):
        return False


@contextlib.asynccontextmanager
async def deferring_app() -> AsyncIterator[procrastinate.App]:
    """Yield the shared app, opening a pool only when one is not already open.

    ``app.open_async()`` is a no-op when the pool exists, but leaving its context
    always closes the pool. Inside the Procrastinate worker that would tear down
    the worker's own pool, so ``finish_job`` then raises ``AppNotOpen`` and the
    worker process dies between chained batch steps.
    """
    if _pool_is_open():
        yield app
        return
    async with app.open_async():
        yield app


# Register task definitions on the shared app instance.
from src.api.batch import tasks as _tasks  # noqa: E402, F401
