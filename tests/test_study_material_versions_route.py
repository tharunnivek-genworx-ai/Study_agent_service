from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.api.rest.routes.study_agent_routes import study_material_route


@pytest.mark.asyncio
async def test_include_archived_requests_both_version_shelves() -> None:
    node_id = uuid4()
    mentor_id = uuid4()
    expected = MagicMock()

    with patch.object(study_material_route, "StudyMaterialService") as service_class:
        service_class.return_value.list_versions = AsyncMock(return_value=expected)
        result = await study_material_route.list_study_material_versions(
            node_id=node_id,
            archived=False,
            include_archived=True,
            viewing_version_id=None,
            db=MagicMock(),
            current_user=MagicMock(sub=mentor_id, role="mentor"),
        )

    assert result is expected
    service_class.return_value.list_versions.assert_awaited_once_with(
        node_id,
        mentor_id,
        "mentor",
        archived=None,
        viewing_version_id=None,
    )
