"""Server-side allowed actions for mentor study-material UI."""

from __future__ import annotations

from uuid import UUID

from src.api.schemas.study_material_schemas.study_material_schema import (
    VersionAllowedActionsOut,
)


def compute_version_allowed_actions(
    *,
    version_id: UUID,
    version_number: int,
    is_active: bool,
    is_published: bool,
    is_archived: bool,
    active_version_id: UUID | None,
    viewing_version_id: UUID | None,
    published_version_id: UUID | None = None,
    published_version_number: int | None = None,
    space_is_published: bool = True,
    content: str | None = None,
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
    can_unpublish = is_published and not is_archived

    publish_disabled_tooltip: str | None = None
    can_publish = not is_published and not is_archived and space_is_published
    if not is_published and not is_archived and not space_is_published:
        can_publish = False
        publish_disabled_tooltip = (
            "Re-publish this space first to make content visible to students."
        )

    # Disable edit and publish if reference material is required
    if content and "GENERATION STATUS: Reference material required" in content:
        can_edit_active_draft = False
        can_publish = False
        publish_disabled_tooltip = (
            "Reference material required to generate study material before publishing."
        )

    publish_button_label = "Make live for students"
    if not is_published and published_version_id is not None:
        if (
            published_version_id != version_id
            and published_version_number is not None
            and version_number < published_version_number
        ):
            publish_button_label = "Restore as live version"
        elif published_version_id != version_id:
            publish_button_label = "Replace live version"

    unpublish_button_label = "Remove from students"
    unpublish_tooltip: str | None = None
    unpublish_disabled_tooltip: str | None = None
    if can_unpublish:
        unpublish_tooltip = (
            "Students will no longer see this topic. "
            "This version returns to your drafts and does not appear in "
            "Previous versions."
        )

    return VersionAllowedActionsOut(
        version_id=version_id,
        can_publish=can_publish,
        can_unpublish=can_unpublish,
        can_archive=can_archive,
        can_edit_active_draft=can_edit_active_draft,
        is_viewing_non_active=is_viewing_non_active,
        is_viewing_archived=is_viewing_archived,
        publish_button_label=publish_button_label,
        publish_disabled_tooltip=publish_disabled_tooltip,
        unpublish_button_label=unpublish_button_label,
        unpublish_tooltip=unpublish_tooltip,
        unpublish_disabled_tooltip=unpublish_disabled_tooltip,
    )
