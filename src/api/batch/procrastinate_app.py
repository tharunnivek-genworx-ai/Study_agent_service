"""Procrastinate application for durable generate-all batch processing."""

from __future__ import annotations

import procrastinate

from src.api.config.dbconfig import build_procrastinate_conninfo

app = procrastinate.App(
    connector=procrastinate.PsycopgConnector(
        conninfo=build_procrastinate_conninfo(),
    ),
)

# Register task definitions on the shared app instance.
from src.api.batch import tasks as _tasks  # noqa: E402, F401
