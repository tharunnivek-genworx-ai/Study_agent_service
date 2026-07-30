"""Dispatch must not close a Procrastinate pool it does not own.

Chained batch steps call ``dispatch_batch_job`` from inside the worker. Closing
the worker's pool there made ``finish_job`` raise ``AppNotOpen``, killing the
worker between steps.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest


class _RecordingOpenAsync:
    def __init__(self) -> None:
        self.enter_count = 0
        self.exit_count = 0

    def __call__(self):
        outer = self

        class _Ctx:
            async def __aenter__(self):
                outer.enter_count += 1
                return None

            async def __aexit__(self, *args):
                outer.exit_count += 1
                return None

        return _Ctx()


@pytest.mark.asyncio
async def test_defers_without_reopening_when_pool_already_open() -> None:
    from src.api.batch import procrastinate_app

    recorder = _RecordingOpenAsync()

    with (
        patch.object(procrastinate_app, "_pool_is_open", return_value=True),
        patch.object(procrastinate_app.app, "open_async", recorder),
    ):
        async with procrastinate_app.deferring_app() as app:
            assert app is procrastinate_app.app

    assert recorder.enter_count == 0
    assert recorder.exit_count == 0


@pytest.mark.asyncio
async def test_opens_pool_when_not_already_open() -> None:
    from src.api.batch import procrastinate_app

    recorder = _RecordingOpenAsync()

    with (
        patch.object(procrastinate_app, "_pool_is_open", return_value=False),
        patch.object(procrastinate_app.app, "open_async", recorder),
    ):
        async with procrastinate_app.deferring_app():
            pass

    assert recorder.enter_count == 1
    assert recorder.exit_count == 1


@pytest.mark.asyncio
async def test_pool_is_open_false_when_connector_raises_app_not_open() -> None:
    from procrastinate.exceptions import AppNotOpen

    from src.api.batch import procrastinate_app

    class _Connector:
        @property
        def pool(self):
            raise AppNotOpen

    with patch.object(procrastinate_app.app, "connector", _Connector()):
        assert procrastinate_app._pool_is_open() is False


@pytest.mark.asyncio
async def test_dispatch_batch_job_uses_deferring_app() -> None:
    from src.api.batch import dispatcher

    recorder = _RecordingOpenAsync()
    batch_id = uuid4()

    with (
        patch.object(dispatcher.settings, "batch_dispatch_mode", "procrastinate"),
        patch("src.api.batch.procrastinate_app._pool_is_open", return_value=True),
        patch("src.api.batch.procrastinate_app.app.open_async", recorder),
        patch(
            "src.api.batch.tasks.process_batch.defer_async",
            new_callable=AsyncMock,
            return_value=7,
        ) as defer,
    ):
        await dispatcher.dispatch_batch_job(batch_id)

    defer.assert_awaited_once_with(batch_id=str(batch_id))
    assert recorder.enter_count == 0
