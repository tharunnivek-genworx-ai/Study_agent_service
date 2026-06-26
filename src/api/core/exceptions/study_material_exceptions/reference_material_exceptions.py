# C:\CapStone\study_agent_service\src\api\core\exceptions\study_material_exceptions\reference_material_exceptions.py
"""
HTTP exceptions for reference_materials and node_media operations.

These are intentionally kept in one file because both domains are
upload/attach concerns and their exception surfaces are small.
If node_media exceptions grow, split into node_media_exceptions.py.

Naming convention mirrors auth_exceptions.py from Service 1.
"""

from fastapi import HTTPException, status

# ── Reference Material ────────────────────────────────────────────────────────


class ReferenceMaterialNotFoundForDeleteException(HTTPException):
    """
    Raised when a DELETE request targets a material_id that does not
    exist, is already soft-deleted (deleted_at is not None), or does
    not belong to the requesting space/node.
    """

    def __init__(self) -> None:
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="That reference PDF was not found or has already been removed.",
        )


class ReferenceMaterialNodeScopeMismatchException(HTTPException):
    """
    Raised when scope='node' is set but node_id is missing, or when
    scope='space' is set but node_id is also provided.
    Enforced at service layer after schema validation.
    """

    def __init__(self) -> None:
        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Topic-level reference PDFs must be attached to a specific topic. "
                "Space-wide references cannot be tied to a single topic."
            ),
        )


# ── Node Media ────────────────────────────────────────────────────────────────


class NodeMediaNotFoundException(HTTPException):
    """
    Raised when a media_id does not exist or does not belong to the
    specified node. Applies to DELETE and reorder operations.
    """

    def __init__(self) -> None:
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="That media item was not found on this topic.",
        )


class NodeMediaReorderIncompleteException(HTTPException):
    """
    Raised when a reorder payload is missing one or more active media
    items for the node. Mirrors NodeReorderIncompleteException from
    Service 1 — partial reorders are always rejected to prevent
    order_index gaps.
    """

    def __init__(self) -> None:
        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="To reorder topic resources, include every active item in your list.",
        )


class InvalidMediaTypePayloadException(HTTPException):
    """
    Raised when:
      - media_type='image' but no file was uploaded (UploadFile is None).
      - media_type='video_url' or 'article_link' but url is None or empty.
    Cross-field constraint enforced at service layer.
    """

    def __init__(self) -> None:
        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Images require a file upload. Video and article links require a URL."
            ),
        )
