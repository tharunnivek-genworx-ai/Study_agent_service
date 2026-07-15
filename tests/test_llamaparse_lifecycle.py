"""Focused cooperative-abort tests for LlamaParse lifecycle wiring."""

from __future__ import annotations

from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from src.api.core.exceptions import GenerationRunAborted
from src.api.utils.reference_llamaparse_utils.llama_parse_extractor import (
    download_figures,
)


def test_download_figures_aborts_before_remote_parse_submission() -> None:
    client = MagicMock()

    with pytest.raises(GenerationRunAborted):
        download_figures(
            client,
            "file-id",
            reference_material_id=uuid4(),
            node_id=uuid4(),
            stamp="test",
            should_continue=lambda: False,
        )

    client.parsing.create.assert_not_called()


def test_download_figures_reports_remote_job_ids() -> None:
    client = MagicMock()
    client.parsing.create.return_value.id = "parse-job"
    client.parsing.get.return_value.job.status = "FAILED"
    observed: list[tuple[str | None, str | None]] = []

    records, parse_job_id = download_figures(
        client,
        "file-id",
        reference_material_id=uuid4(),
        node_id=uuid4(),
        stamp="test",
        should_continue=lambda: True,
        on_job_ids=lambda extract_id, parse_id: observed.append((extract_id, parse_id)),
        extract_job_id="extract-job",
    )

    assert records == []
    assert parse_job_id == "parse-job"
    assert observed == [("extract-job", "parse-job")]
