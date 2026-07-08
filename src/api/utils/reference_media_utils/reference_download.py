"""Download reference material files for LlamaParse extraction."""

from __future__ import annotations

import asyncio
import os
import tempfile
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

from src.api.utils.storage.object_storage import (
    download_bytes,
    is_local_path,
)


def _download_url_to_path(url: str, destination: Path) -> None:
    with urllib.request.urlopen(url) as response:
        destination.write_bytes(response.read())


async def download_reference_to_temp(
    file_url: str, file_name: str
) -> tuple[Path, bool]:
    """Resolve a reference file to a local path for extraction.

    Returns ``(path, is_temp)`` where ``is_temp`` is True only when a new
    temporary file was created (and the caller is responsible for deleting it).
    When ``file_url`` already points to an existing local file, that original
    path is returned with ``is_temp=False`` so callers never delete the source.
    """
    local_candidate = Path(file_url)
    if is_local_path(file_url) and local_candidate.is_file():
        return local_candidate, False

    suffix = Path(file_name).suffix or ".pdf"
    fd, temp_path_str = tempfile.mkstemp(suffix=suffix)
    os.close(fd)
    temp_path = Path(temp_path_str)

    parsed = urlparse(file_url)
    if parsed.scheme in ("http", "https"):
        await asyncio.to_thread(_download_url_to_path, file_url, temp_path)
        return temp_path, True

    if not is_local_path(file_url):
        data = await download_bytes(file_url)
        temp_path.write_bytes(data)
        return temp_path, True

    raise FileNotFoundError(f"Reference file is not reachable: {file_url}")
