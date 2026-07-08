"""Unit tests for GCS signed URL generation."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import MagicMock, patch

from src.api.utils.storage import gcs_storage


def test_generate_signed_url_uses_iam_signing_on_compute_credentials() -> None:
    credentials = MagicMock()
    credentials.token = "access-token"
    credentials.service_account_email = "gwx-sa@project.iam.gserviceaccount.com"

    blob = MagicMock()
    blob.generate_signed_url.return_value = "https://storage.googleapis.com/signed"

    with (
        patch.object(gcs_storage, "_get_blob", return_value=blob),
        patch.object(gcs_storage, "_refresh_credentials", return_value=credentials),
        patch.object(gcs_storage.settings, "gcs_signed_url_expiry_minutes", 60),
        patch.object(gcs_storage, "Signing", type("Signing", (), {})),
    ):
        url = gcs_storage.generate_signed_url("studyguru/tharun/file.pdf")

    assert url == "https://storage.googleapis.com/signed"
    blob.generate_signed_url.assert_called_once_with(
        version="v4",
        expiration=timedelta(minutes=60),
        method="GET",
        service_account_email="gwx-sa@project.iam.gserviceaccount.com",
        access_token="access-token",
    )
