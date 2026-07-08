"""Unit tests for object storage facade and backends."""

from __future__ import annotations

from unittest.mock import patch
from uuid import uuid4

import pytest

from src.api.utils.storage import object_storage


def test_build_reference_material_key_node_scope() -> None:
    space_id = uuid4()
    node_id = uuid4()
    material_id = uuid4()
    key = object_storage.build_reference_material_key(
        space_id, node_id, material_id, "notes.pdf"
    )
    assert key.endswith(
        f"/reference_materials/{space_id}/{node_id}/{material_id}_notes.pdf"
    )
    assert key.startswith("studyguru/tharun/")


def test_build_reference_material_key_space_scope() -> None:
    space_id = uuid4()
    material_id = uuid4()
    key = object_storage.build_reference_material_key(
        space_id, None, material_id, "guide.pdf"
    )
    assert f"/reference_materials/{space_id}/space/{material_id}_guide.pdf" in key


def test_build_node_media_key() -> None:
    space_id = uuid4()
    node_id = uuid4()
    media_id = uuid4()
    key = object_storage.build_node_media_key(space_id, node_id, media_id, "img.png")
    assert key.endswith(f"/node_media/{space_id}/{node_id}/{media_id}_img.png")


def test_build_llamaparse_image_key() -> None:
    material_id = uuid4()
    node_id = uuid4()
    key = object_storage.build_llamaparse_image_key(
        material_id, node_id, "20260101_120000", "page_1_chart_1.png"
    )
    assert (
        key == f"studyguru/tharun/reference_llamaparse/{material_id}/{node_id}/"
        f"images_20260101_120000/page_1_chart_1.png"
    )


def test_is_local_path() -> None:
    assert object_storage.is_local_path("/app/uploads/reference_materials/x.pdf")
    assert not object_storage.is_local_path(
        "studyguru/tharun/reference_materials/x.pdf"
    )
    assert not object_storage.is_local_path("https://storage.googleapis.com/bucket/x")


@pytest.mark.asyncio
async def test_upload_bytes_routes_to_local_backend() -> None:
    with (
        patch.object(object_storage.settings, "gcs_bucket", ""),
        patch(
            "src.api.utils.storage.object_storage.local_storage.upload_bytes",
            return_value="/app/uploads/test.pdf",
        ) as local_upload,
    ):
        result = await object_storage.upload_bytes(
            "studyguru/tharun/key.pdf", b"data", "application/pdf"
        )
    local_upload.assert_called_once_with(
        "studyguru/tharun/key.pdf", b"data", "application/pdf"
    )
    assert result == "/app/uploads/test.pdf"


@pytest.mark.asyncio
async def test_upload_bytes_routes_to_gcs_backend() -> None:
    with (
        patch.object(object_storage.settings, "gcs_bucket", "my-bucket"),
        patch(
            "src.api.utils.storage.object_storage.gcs_storage.upload_bytes",
            return_value="studyguru/tharun/key.pdf",
        ) as gcs_upload,
    ):
        result = await object_storage.upload_bytes(
            "studyguru/tharun/key.pdf", b"data", "application/pdf"
        )
    gcs_upload.assert_called_once_with(
        "studyguru/tharun/key.pdf", b"data", "application/pdf"
    )
    assert result == "studyguru/tharun/key.pdf"


@pytest.mark.asyncio
async def test_download_bytes_local_path() -> None:
    with patch(
        "src.api.utils.storage.object_storage.local_storage.download_bytes",
        return_value=b"local-bytes",
    ) as local_download:
        data = await object_storage.download_bytes("/app/uploads/file.pdf")
    local_download.assert_called_once_with("/app/uploads/file.pdf")
    assert data == b"local-bytes"


@pytest.mark.asyncio
async def test_download_bytes_gcs_key() -> None:
    with (
        patch.object(object_storage.settings, "gcs_bucket", "my-bucket"),
        patch(
            "src.api.utils.storage.object_storage.gcs_storage.download_bytes",
            return_value=b"gcs-bytes",
        ) as gcs_download,
    ):
        data = await object_storage.download_bytes("studyguru/tharun/file.pdf")
    gcs_download.assert_called_once_with("studyguru/tharun/file.pdf")
    assert data == b"gcs-bytes"


def test_resolve_public_url_local() -> None:
    with (
        patch.object(object_storage.settings, "gcs_bucket", ""),
        patch.object(
            object_storage.settings, "media_base_url", "http://localhost:8001"
        ),
    ):
        url = object_storage.resolve_public_url(
            "/app/uploads/reference_materials/a.pdf"
        )
    assert url == "http://localhost:8001/uploads/reference_materials/a.pdf"


def test_resolve_public_url_gcs_uses_media_access_url() -> None:
    with (
        patch.object(object_storage.settings, "gcs_bucket", "my-bucket"),
        patch.object(
            object_storage.settings, "media_base_url", "http://localhost:8001"
        ),
        patch(
            "src.api.utils.storage.object_storage.media_access_url",
            return_value="http://localhost:8001/media/file?token=abc",
        ) as media_url,
    ):
        url = object_storage.resolve_public_url("studyguru/tharun/file.pdf")
    media_url.assert_called_once_with("studyguru/tharun/file.pdf")
    assert url == "http://localhost:8001/media/file?token=abc"


def test_generate_signed_url_delegates_to_gcs() -> None:
    with patch(
        "src.api.utils.storage.object_storage.gcs_storage.generate_signed_url",
        return_value="https://signed.example",
    ) as signed:
        url = object_storage.generate_signed_url("studyguru/tharun/x.pdf")
    signed.assert_called_once_with("studyguru/tharun/x.pdf")
    assert url == "https://signed.example"


@pytest.mark.asyncio
async def test_exists_routes_to_gcs() -> None:
    with (
        patch.object(object_storage.settings, "gcs_bucket", "my-bucket"),
        patch(
            "src.api.utils.storage.object_storage.gcs_storage.exists",
            return_value=True,
        ) as gcs_exists,
    ):
        found = await object_storage.exists("studyguru/tharun/file.pdf")
    gcs_exists.assert_called_once_with("studyguru/tharun/file.pdf")
    assert found is True
