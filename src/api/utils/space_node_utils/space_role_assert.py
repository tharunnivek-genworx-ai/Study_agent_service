from typing import cast
from uuid import UUID

from src.api.data.models.postgres.e_spaces_trees.espaces import ESpace


def _resolve_effective_mentor(space: ESpace) -> UUID:
    """COALESCE(transferred_to_mentor_id, mentor_id)."""
    return cast(
        UUID,
        space.transferred_to_mentor_id
        if space.transferred_to_mentor_id
        else space.mentor_id,
    )
