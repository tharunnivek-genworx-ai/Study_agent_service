"""Parity tests for server-owned mentor History Hub eligibility."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from src.api.core.services.study_agent_services.study_material_service import (
    _compute_show_history_hub,
)


def _version(**kwargs: object) -> SimpleNamespace:
    defaults = {
        "lifecycle_status": "draft",
        "is_active": False,
        "is_published": False,
        "is_archived": False,
        "published_at": None,
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def _published_at() -> datetime:
    return datetime(2026, 1, 1, tzinfo=UTC)


@pytest.mark.parametrize(
    ("versions", "expected"),
    [
        pytest.param([], False, id="empty"),
        pytest.param(
            [
                _version(
                    lifecycle_status="active",
                    is_published=True,
                    published_at=_published_at(),
                )
            ],
            False,
            id="live-only",
        ),
        pytest.param(
            [
                _version(),
                _version(
                    lifecycle_status="archived",
                    published_at=_published_at(),
                ),
            ],
            False,
            id="workspace-draft-plus-history",
        ),
        pytest.param(
            [
                _version(
                    lifecycle_status="archived",
                    published_at=_published_at(),
                )
            ],
            True,
            id="previous-only",
        ),
        pytest.param(
            [
                _version(
                    lifecycle_status="hidden",
                    published_at=_published_at(),
                )
            ],
            True,
            id="removed-only",
        ),
        pytest.param(
            [_version(is_archived=True)],
            True,
            id="mentor-archive-only",
        ),
        pytest.param(
            [
                _version(
                    lifecycle_status="archived",
                    is_active=True,
                    published_at=_published_at(),
                )
            ],
            True,
            id="stale-active-points-at-previous",
        ),
    ],
)
def test_history_hub_eligibility_matches_frontend_parity_fixtures(
    versions: list[SimpleNamespace],
    expected: bool,
) -> None:
    assert _compute_show_history_hub(versions) is expected
