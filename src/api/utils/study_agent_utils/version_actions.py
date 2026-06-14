"""Server-side allowed actions for mentor study-material UI."""

from __future__ import annotations

from uuid import UUID

from src.api.schemas.study_material_schemas.study_material_schema import (
    VersionAllowedActionsOut,
)


def compute_version_allowed_actions(
    *,
    version_id: UUID,
    is_active: bool,
    is_published: bool,
    is_archived: bool,
    active_version_id: UUID | None,
    viewing_version_id: UUID | None,
) -> VersionAllowedActionsOut:
    is_viewing_non_active = bool(
        viewing_version_id
        and active_version_id
        and viewing_version_id != active_version_id
    )
    is_viewing_archived = is_archived

    can_edit_active_draft = (
        is_active and not is_viewing_non_active and not is_viewing_archived
    )
    can_archive = not is_published and not is_archived
    can_publish = not is_published and not is_archived
    can_unpublish = is_published and not is_archived

    return VersionAllowedActionsOut(
        version_id=version_id,
        can_publish=can_publish,
        can_unpublish=can_unpublish,
        can_archive=can_archive,
        can_edit_active_draft=can_edit_active_draft,
        is_viewing_non_active=is_viewing_non_active,
        is_viewing_archived=is_viewing_archived,
    )
