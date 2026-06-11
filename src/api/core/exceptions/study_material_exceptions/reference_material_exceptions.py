# src/api/core/exceptions/content_exceptions/reference_material_exceptions.py
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
            detail="Reference material not found or already removed.",
        )


class ReferenceMaterialForbiddenException(HTTPException):
    """
    Raised when a mentor tries to upload, delete, or update visibility
    for a reference material in a space they do not own.
    """

    def __init__(self) -> None:
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to manage materials for this space.",
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
                "Scope/node_id mismatch: "
                "scope='node' requires a node_id; scope='space' must omit node_id."
            ),
        )


class UnsupportedFileTypeException(HTTPException):
    """
    Raised when an uploaded file's MIME type is not in the allowed set
    (application/pdf, application/vnd.ms-powerpoint, etc.).
    The allowed MIME types are defined in the service config, not here.
    """

    def __init__(self, mime_type: str) -> None:
        super().__init__(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"File type '{mime_type}' is not supported for reference materials.",
        )


class FileSizeLimitExceededException(HTTPException):
    """
    Raised when an uploaded file exceeds the configured maximum size
    (e.g., 50 MB). Limit is read from service config at the upload handler.
    """

    def __init__(self, max_mb: int) -> None:
        super().__init__(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds the maximum allowed size of {max_mb} MB.",
        )


class GCSUploadFailedException(HTTPException):
    """
    Raised when the Google Cloud Storage upload call fails after retries.
    The file is not saved to the DB if GCS upload fails — atomicity is
    enforced at the service layer (upload first, then insert DB row).
    """

    def __init__(self) -> None:
        super().__init__(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="File upload failed. Please try again.",
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
            detail="Media item not found.",
        )


class NodeMediaForbiddenException(HTTPException):
    """
    Raised when a mentor tries to attach or remove media for a node
    in a space they do not own.
    """

    def __init__(self) -> None:
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to manage media for this node.",
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
            detail="Reorder payload must include all active media items for this node.",
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
                "Invalid media payload: 'image' type requires a file upload; "
                "'video_url' and 'article_link' types require a url."
            ),
        )
