# tests/test_qc_retry_audit.py
"""Unit tests for QC retry audit payload builders."""

from __future__ import annotations

from src.api.schemas.qc_schemas import RetryRoutingResult
from src.api.utils.study_agent_utils.graph import node_helpers as helpers
from src.api.utils.study_agent_utils.quality_check_utils.infra.qc_retry_audit import (
    build_qc_result_log_payload,
    build_qc_retry_context,
    build_study_retry_input_audit,
    retry_feedback_channel,
    should_attach_study_retry_audit,
)


def _qc_result(*, failed_checks: list[dict] | None = None) -> dict:
    checks = failed_checks or [
        {
            "id": "mc_1",
            "category": "must_cover",
            "passed": False,
            "severity": "critical",
            "question": "Cover topic?",
            "evidence": "Missing depth",
            "corrective_hint": "Add detail",
        }
    ]
    return {"failed_checks": checks, "checks": checks}


def _routing(*, mode: str = "section_patch") -> RetryRoutingResult:
    return RetryRoutingResult(
        mode=mode,  # type: ignore[arg-type]
        failed_section_ids=["ts_1"],
        missing_checklist_ids=[],
        section_failures=[{"section_id": "ts_1", "failures": []}],
        rationale=f"deterministic routing: {mode}",
    )


class TestRetryFeedbackChannel:
    def test_section_patch_modes(self) -> None:
        for mode in (
            "section_patch",
            "section_insert",
            "section_patch_then_insert",
        ):
            assert retry_feedback_channel(mode) == "structured_section_failures"

    def test_full_regeneration(self) -> None:
        assert retry_feedback_channel("full_regeneration") == "flat_qc_feedback"

    def test_none(self) -> None:
        assert retry_feedback_channel("none") == "none"


class TestBuildQcRetryContext:
    def test_fail_includes_feedback_and_routing(self) -> None:
        qc_result = _qc_result()
        routing = _routing(mode="section_patch")
        ctx = build_qc_retry_context(
            qc_result=qc_result,
            routing=routing,
            passed=False,
            qc_attempt=1,
            pipeline_attempt=1,
        )
        assert ctx["retry_feedback_channel"] == "structured_section_failures"
        assert ctx["prompt_channel"]["structured_section_failures"] is True
        assert ctx["prompt_channel"]["flat_qc_feedback"] is False
        assert "Failed Checks:" in ctx["qc_feedback"]
        assert ctx["retry_routing"]["mode"] == "section_patch"
        assert ctx["retry_routing"]["rationale"] == routing.rationale
        assert ctx["retry_routing"]["section_failures"] == routing.section_failures
        assert ctx["next_study_pipeline_attempt"] == 2

    def test_full_regen_channel(self) -> None:
        ctx = build_qc_retry_context(
            qc_result=_qc_result(),
            routing=_routing(mode="full_regeneration"),
            passed=False,
            qc_attempt=2,
            pipeline_attempt=2,
        )
        assert ctx["retry_feedback_channel"] == "flat_qc_feedback"
        assert ctx["next_study_pipeline_attempt"] == 3

    def test_pass_clears_retry_fields(self) -> None:
        ctx = build_qc_retry_context(
            qc_result=_qc_result(),
            routing=_routing(),
            passed=True,
            qc_attempt=1,
            pipeline_attempt=1,
        )
        assert ctx["retry_feedback_channel"] == "none"
        assert ctx["qc_feedback"] == ""
        assert ctx["retry_routing"]["mode"] == "none"
        assert ctx["next_study_pipeline_attempt"] is None


class TestBuildQcResultLogPayload:
    def test_merges_base_fields(self) -> None:
        payload = build_qc_result_log_payload(
            qc_result=_qc_result(),
            routing=_routing(),
            passed=False,
            qc_attempt=1,
            pipeline_attempt=1,
            qc_passed=False,
            overall_status="fail",
            verification_mode="full",
            qc_retry_mode="section_patch",
        )
        assert payload["qc_passed"] is False
        assert payload["overall_status"] == "fail"
        assert payload["retry_feedback_channel"] == "structured_section_failures"
        assert "qc_result" in payload
        assert "retry_routing" in payload


class TestBuildStudyRetryInputAudit:
    def test_section_patch_audit(self) -> None:
        state = {
            "qc_attempt": 1,
            "qc_retry_mode": "section_patch",
            "qc_section_failures": [{"section_id": "ts_1", "failures": []}],
            "qc_reverify_section_ids": ["ts_1"],
            "qc_missing_checklist_ids": [],
            "qc_feedback": "unused flat text",
        }
        audit = build_study_retry_input_audit(state)  # type: ignore[arg-type]
        assert audit["triggered_by_qc_attempt"] == 1
        assert audit["retry_feedback_channel"] == "structured_section_failures"
        assert audit["feedback_blocks"]["quality_check_feedback"] is False
        assert audit["feedback_blocks"]["sections_to_fix"] == 1
        assert audit["retry_input"]["in_run_qc_feedback_source"] == "pipeline_qc_fail"

    def test_full_regen_audit(self) -> None:
        state = {
            "qc_attempt": 1,
            "qc_retry_mode": "full_regeneration",
            "qc_feedback": "Failed Checks:\n  - [critical] x",
            "qc_section_failures": [],
        }
        audit = build_study_retry_input_audit(state)  # type: ignore[arg-type]
        assert audit["retry_feedback_channel"] == "flat_qc_feedback"
        assert audit["feedback_blocks"]["quality_check_feedback"] is True

    def test_db_hydrated_feedback(self) -> None:
        state = {
            "qc_attempt": 0,
            "qc_retry_mode": "none",
            "failed_qc_feedback": "Previously failed",
        }
        audit = build_study_retry_input_audit(state)  # type: ignore[arg-type]
        assert (
            audit["feedback_blocks"]["previous_failed_quality_check_feedback"] is True
        )
        assert audit["retry_input"]["failed_qc_feedback_source"] == "db_hydration"


class TestShouldAttachStudyRetryAudit:
    def test_qc_attempt_triggers(self) -> None:
        assert should_attach_study_retry_audit({"qc_attempt": 1}) is True  # type: ignore[arg-type]

    def test_failed_db_feedback_triggers(self) -> None:
        assert should_attach_study_retry_audit(  # type: ignore[arg-type]
            {"qc_attempt": 0, "failed_qc_feedback": "x"}
        )

    def test_initial_generate_skips(self) -> None:
        assert should_attach_study_retry_audit({"qc_attempt": 0}) is False  # type: ignore[arg-type]


class TestBuildQcFeedbackBlockReferenceDedup:
    def test_no_duplicate_reference_block(self) -> None:
        state = {
            "qc_retry_mode": "full_regeneration",
            "qc_attempt": 1,
            "qc_feedback": "Fix the document",
            "generated_content": '{"sections": []}',
            "extracted_reference_text": "Reference body text",
            "has_reference_material": True,
        }
        block = helpers.build_qc_feedback_block(state)  # type: ignore[arg-type]
        assert "<quality_check_feedback>" in block
        assert "<previous_draft_json>" in block
        assert "reference_material_for_correction" not in block
