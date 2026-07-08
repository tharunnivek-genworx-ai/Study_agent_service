"""Tests for app-signed media access tokens."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import jwt
import pytest

from src.api.config import settings
from src.api.utils.storage.media_access_token import (
    create_media_access_token,
    decode_media_access_token,
    media_access_url,
)


def test_media_access_token_roundtrip() -> None:
    storage_ref = "studyguru/tharun/node_media/space/node/file.png"
    token = create_media_access_token(storage_ref)
    assert decode_media_access_token(token) == storage_ref


def test_media_access_token_rejects_wrong_type() -> None:
    token = jwt.encode(
        {
            "typ": "access",
            "ref": "studyguru/tharun/file.pdf",
            "exp": datetime.now(UTC) + timedelta(minutes=5),
        },
        settings.secret_key,
        algorithm=settings.algorithm,
    )
    with pytest.raises(jwt.InvalidTokenError):
        decode_media_access_token(token)


def test_media_access_url_includes_token_query() -> None:
    url = media_access_url("studyguru/tharun/file.pdf")
    assert url.startswith(f"{settings.media_base_url.rstrip('/')}/media/file?token=")
