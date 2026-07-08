"""Google Cloud Storage backend using Application Default Credentials."""

from __future__ import annotations

from datetime import timedelta
from typing import cast

import google.auth
import google.auth.transport.requests
from google.auth.credentials import Signing
from google.cloud import storage

from src.api.config import settings

_client: storage.Client | None = None


def _get_client() -> storage.Client:
    global _client
    if _client is None:
        _client = storage.Client()
    return _client


def _get_blob(storage_ref: str) -> storage.Blob:
    bucket = _get_client().bucket(settings.gcs_bucket)
    return bucket.blob(storage_ref)


def _refresh_credentials() -> google.auth.credentials.Credentials:
    credentials, _project = google.auth.default(
        scopes=["https://www.googleapis.com/auth/cloud-platform"]
    )
    auth_request = google.auth.transport.requests.Request()
    credentials.refresh(auth_request)
    return credentials


def upload_bytes(key: str, data: bytes, content_type: str) -> str:
    """Upload bytes to GCS and return the object key."""
    blob = _get_blob(key)
    blob.upload_from_string(data, content_type=content_type)
    return key


def download_bytes(storage_ref: str) -> bytes:
    """Download object bytes from GCS."""
    return cast(bytes, _get_blob(storage_ref).download_as_bytes())


def exists(storage_ref: str) -> bool:
    """Return True when the object exists in GCS."""
    return cast(bool, _get_blob(storage_ref).exists())


def generate_signed_url(storage_ref: str) -> str:
    """Return a time-limited signed GET URL for an object key."""
    blob = _get_blob(storage_ref)
    expiration = timedelta(minutes=settings.gcs_signed_url_expiry_minutes)
    signing_kwargs: dict[str, object] = {
        "version": "v4",
        "expiration": expiration,
        "method": "GET",
    }

    credentials = _refresh_credentials()
    if isinstance(credentials, Signing):
        signing_kwargs["credentials"] = credentials
    else:
        service_account_email = getattr(credentials, "service_account_email", None)
        if not service_account_email:
            raise RuntimeError(
                "Cannot resolve service account email for GCS signed URLs"
            )
        signing_kwargs["service_account_email"] = service_account_email
        signing_kwargs["access_token"] = credentials.token

    return cast(str, blob.generate_signed_url(**signing_kwargs))
