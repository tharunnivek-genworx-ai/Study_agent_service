"""Public media streaming via time-limited access tokens."""

from __future__ import annotations

import mimetypes

import jwt
from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import Response

from src.api.core.exceptions import InvalidTokenException
from src.api.utils.storage.media_access_token import decode_media_access_token
from src.api.utils.storage.object_storage import download_bytes, exists

router = APIRouter(tags=["Media Access"])


@router.get("/media/file")
async def stream_media_file(
    token: str = Query(..., min_length=1),
) -> Response:
    """Stream a stored object when presented with a valid media access token."""
    try:
        storage_ref = decode_media_access_token(token)
    except (InvalidTokenException, jwt.InvalidTokenError):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Media access link is invalid or expired.",
        ) from None

    if not await exists(storage_ref):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Media file not found.",
        )

    content = await download_bytes(storage_ref)
    filename = storage_ref.rsplit("/", 1)[-1]
    mime_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    return Response(
        content=content,
        media_type=mime_type,
        headers={"Cache-Control": "private, max-age=300"},
    )
