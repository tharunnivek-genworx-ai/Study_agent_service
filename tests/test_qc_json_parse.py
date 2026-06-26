# tests/test_qc_json_parse.py
"""Unit tests for hardened QC JSON parsing."""

from __future__ import annotations

import json
from pathlib import Path

from src.api.utils.study_agent_utils.quality_check_utils.parsing.json_parse import (
    is_valid_qc_verification_response,
    parse_llm_json_object,
    parse_qc_verification_response,
)


class TestParseLlmJsonObject:
    def test_plain_object(self):
        assert parse_llm_json_object('{"a": 1}') == {"a": 1}

    def test_markdown_fence(self):
        raw = '```json\n{"checks": [], "summary": "ok"}\n```'
        parsed = parse_llm_json_object(raw)
        assert parsed is not None
        assert parsed.get("summary") == "ok"

    def test_trailing_junk_after_valid_json(self):
        raw = '{"summary": "done"}\n}'
        parsed = parse_llm_json_object(raw)
        assert parsed == {"summary": "done"}

    def test_extra_closing_brace_repair(self):
        raw = '{\n  "summary": "x"\n  }\n}'
        parsed = parse_llm_json_object(raw)
        assert parsed is not None
        assert parsed.get("summary") == "x"

    def test_oops_artifact_verification_response(self):
        path = (
            Path(__file__).resolve().parents[2]
            / "uploads"
            / "artifacts"
            / "OOPS_SMG"
            / "run_20260624_101406"
            / "attempt01"
            / "04_qc_verification.json"
        )
        if not path.exists():
            path = (
                Path(__file__).resolve().parents[1].parent
                / "uploads"
                / "artifacts"
                / "OOPS_SMG"
                / "run_20260624_101406"
                / "attempt01"
                / "04_qc_verification.json"
            )
        if not path.exists():
            return
        data = json.loads(path.read_text(encoding="utf-8"))
        parsed = parse_llm_json_object(data["raw_response"], "QC verification")
        assert parsed is not None
        assert isinstance(parsed.get("checks"), list)
        assert len(parsed["checks"]) > 0


class TestQcVerificationValidation:
    def test_rejects_missing_checks_key(self):
        obj = {"summary": "x", "hallucination_risk": "none", "is_refusal": False}
        assert is_valid_qc_verification_response(obj) is False
        assert parse_qc_verification_response(json.dumps(obj)) is None

    def test_accepts_checks_list(self):
        obj = {
            "checks": [{"id": "1", "category": "must_cover", "passed": True}],
            "hallucination_risk": "none",
            "is_refusal": False,
        }
        assert is_valid_qc_verification_response(obj) is True

    def test_rejects_empty_checks_when_not_refusal(self):
        obj = {"checks": [], "hallucination_risk": "none", "is_refusal": False}
        assert is_valid_qc_verification_response(obj) is False

    def test_accepts_empty_checks_for_refusal(self):
        obj = {"checks": [], "is_refusal": True}
        assert is_valid_qc_verification_response(obj) is True
