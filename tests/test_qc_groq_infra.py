# tests/test_qc_groq_infra.py
"""Tests for Groq key-rotation diagnostics and QC TPM budgeting."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from langchain_core.messages import HumanMessage, SystemMessage

from src.api.utils.LLM_utils import groq_qc_client
from src.api.utils.LLM_utils.groq_retry import GroqCallResult
from src.api.utils.LLM_utils.llm_failure_diagnostics import build_llm_failure_qc_result
from src.api.utils.study_agent_utils.quality_check_utils.infra.infra_failure import (
    build_infra_failure_return,
    resolve_qc_infra_error_type,
)


class TestQcGroqTpmBudget:
    def test_effective_max_tokens_stays_under_groq_tpm_limit(self, monkeypatch):
        monkeypatch.setattr(groq_qc_client.llm_settings, "qc_llm_max_tokens", 12288)
        monkeypatch.setattr(groq_qc_client.llm_settings, "groq_qc_tpm_limit", 12000)
        # ~4050 input tokens (matches the user's failing QC request shape)
        messages = [
            SystemMessage(content="x" * 16200),
            HumanMessage(content="y" * 100),
        ]
        max_tokens = groq_qc_client._effective_qc_max_tokens(messages)
        estimated_input = groq_qc_client._estimate_input_tokens(messages)
        assert estimated_input + max_tokens <= 12000
        assert max_tokens < 12288

    def test_effective_max_tokens_respects_configured_ceiling(self, monkeypatch):
        monkeypatch.setattr(groq_qc_client.llm_settings, "qc_llm_max_tokens", 4096)
        monkeypatch.setattr(groq_qc_client.llm_settings, "groq_qc_tpm_limit", 12000)
        messages = [HumanMessage(content="short prompt")]
        assert groq_qc_client._effective_qc_max_tokens(messages) == 4096


class TestResolveQcInfraErrorType:
    def test_maps_groq_rate_limit(self):
        assert resolve_qc_infra_error_type("rate_limited") == "rate_limited"

    def test_maps_unknown_to_qc_verification_failed(self):
        assert resolve_qc_infra_error_type("something_else") == "qc_verification_failed"


class TestBuildInfraFailureReturn:
    def test_propagates_groq_result_fields(self):
        retry_at = datetime(2026, 6, 25, 12, 0, tzinfo=UTC)
        groq_result = GroqCallResult(
            ok=False,
            error_type="rate_limited",
            provider_meta={"api_key_alias": "key_2", "graph_node": "qc_verification"},
            retry_after_seconds=60,
            next_llm_retry_at=retry_at,
            suggestion="Shorten generated content sent to QC or reduce reference scope.",
            model="llama-3.3-70b-versatile",
            graph_node="qc_verification",
        )
        result = build_infra_failure_return(
            new_attempt=1,
            extraction_snapshot={"sections": []},
            groq_result=groq_result,
        )
        assert result["llm_error_type"] == "rate_limited"
        assert result["next_llm_retry_at"] == retry_at
        assert result["qc_result"]["errorType"] == "rate_limited"
        assert result["qc_result"]["qcInfraError"] is True
        assert result["qc_result"]["retryAfterSeconds"] == 60
        assert result["qc_result"]["suggestion"]

    def test_qc_result_is_json_serializable_for_db_persist(self):
        retry_at = datetime(2026, 6, 25, 12, 0, tzinfo=UTC)
        groq_result = GroqCallResult(
            ok=False,
            error_type="rate_limited",
            provider_meta={
                "api_key_alias": "key_2",
                "graph_node": "qc_verification",
                "next_llm_retry_at": retry_at,
            },
            retry_after_seconds=60,
            next_llm_retry_at=retry_at,
            suggestion="Retry later.",
            model="llama-3.3-70b-versatile",
            graph_node="qc_verification",
        )
        result = build_infra_failure_return(
            new_attempt=1,
            extraction_snapshot={"sections": []},
            groq_result=groq_result,
        )
        serialized = json.dumps(result["qc_result"])
        assert "2026-06-25T12:00:00" in serialized
        assert isinstance(result["qc_result"]["nextLlmRetryAt"], str)

    def test_build_llm_failure_qc_result_is_json_serializable(self):
        retry_at = datetime(2026, 6, 25, 12, 0, tzinfo=UTC)
        groq_result = GroqCallResult(
            ok=False,
            error_type="llm_infra_error",
            provider_meta={
                "api_key_alias": "key_1",
                "attempt_index": 2,
                "graph_node": "study_generator",
                "next_llm_retry_at": retry_at,
            },
            retry_after_seconds=30,
            next_llm_retry_at=retry_at,
            suggestion="Try again.",
            model="llama-3.3-70b-versatile",
            graph_node="study_generator",
        )
        qc_result = build_llm_failure_qc_result(groq_result)
        serialized = json.dumps(qc_result)
        assert isinstance(qc_result["nextLlmRetryAt"], str)
        assert "2026-06-25T12:00:00" in serialized
