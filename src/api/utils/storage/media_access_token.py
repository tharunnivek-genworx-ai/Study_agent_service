"""Time-limited JWTs for streaming GCS objects without IAM signBlob."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import cast
from urllib.parse import quote

import jwt

from src.api.config import settings
from src.api.utils.common_utils.tokens import decode_token


def create_media_access_token(storage_ref: str) -> str:
    """Return a signed token authorizing read access to one storage object."""
    expire = datetime.now(UTC) + timedelta(
        minutes=settings.gcs_signed_url_expiry_minutes
    )
    payload = {
        "typ": "media",
        "ref": storage_ref,
        "exp": expire,
    }
    return cast(
        str, jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)
    )


def decode_media_access_token(token: str) -> str:
    """Validate a media token and return the authorized storage reference."""
    payload = decode_token(
        token,
        expired_message="Media access link has expired.",
        invalid_message="Media access link is invalid.",
    )
    if payload.get("typ") != "media":
        raise jwt.InvalidTokenError("Not a media access token.")
    storage_ref = payload.get("ref")
    if not isinstance(storage_ref, str) or not storage_ref:
        raise jwt.InvalidTokenError("Media token is missing a storage reference.")
    return storage_ref


def media_access_url(storage_ref: str) -> str:
    """Build a browser-loadable URL that streams the object through this service."""
    token = create_media_access_token(storage_ref)
    base = settings.media_base_url.rstrip("/")
    return f"{base}/media/file?token={quote(token, safe='')}"
