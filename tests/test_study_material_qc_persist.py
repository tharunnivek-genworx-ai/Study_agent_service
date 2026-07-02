# tests/test_study_material_qc_persist.py
"""Tests for QC persistence and regenerate/improve hydration."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.api.control.study_agent.nodes.concept_checklist_node import (
    concept_checklist_node,
)
from src.api.core.services.study_agent_services.study_material_service import (
    _build_concept_plan_from_graph,
    _hydration_from_active_version,
    _resolve_qc_result_for_persist,
    _study_material_version_out,
)
from src.api.data.repositories.study_agent_repositories.study_material_repository import (
    StudyMaterialRepository,
)


def test_resolve_qc_result_persists_on_qc_pass() -> None:
    graph_result = {
        "qc_attempt": 2,
        "qc_passed": True,
        "qc_evaluated": True,
        "qc_failed_permanently": False,
        "must_cover_checklist": [{"id": "c1", "concept": "loops"}],
        "checklist_llm_model_used": "llama-3.3-70b-versatile",
        "qc_verification_mode": "targeted",
        "qc_result": {
            "overall_status": "pass",
            "scores": {
                "structure": 8,
                "content_accuracy": 9,
                "teaching_alignment": 10,
            },
            "checks": [],
        },
    }

    failed_permanently, qc_dict = _resolve_qc_result_for_persist(graph_result)

    assert failed_permanently is False
    assert qc_dict is not None
    assert qc_dict["overall_status"] == "pass"
    assert "structure" not in (qc_dict.get("scores") or {})
    assert qc_dict["scores"]["content_accuracy"] == 9
    assert qc_dict["must_cover_checklist"] == [{"id": "c1", "concept": "loops"}]
    assert qc_dict["verification_mode"] == "targeted"


def test_resolve_qc_result_permanent_failure_still_persists() -> None:
    graph_result = {
        "qc_attempt": 3,
        "qc_passed": False,
        "qc_evaluated": True,
        "qc_failed_permanently": True,
        "terminal_llm_failure": True,
        "qc_result": {
            "overall_status": "fail",
            "scores": {"structure": 3, "content_accuracy": 2},
            "checks": [],
        },
    }

    failed_permanently, qc_dict = _resolve_qc_result_for_persist(graph_result)

    assert failed_permanently is True
    assert qc_dict is not None
    assert "structure" not in (qc_dict.get("scores") or {})


def test_resolve_qc_result_none_when_qc_not_evaluated() -> None:
    failed_permanently, qc_dict = _resolve_qc_result_for_persist(
        {
            "qc_attempt": 2,
            "qc_passed": False,
            "qc_evaluated": False,
            "generation_outcome": "reference_required",
        }
    )
    assert failed_permanently is False
    assert qc_dict is None


def test_resolve_qc_result_none_when_qc_never_ran() -> None:
    failed_permanently, qc_dict = _resolve_qc_result_for_persist(
        {"qc_attempt": 0, "qc_passed": False, "qc_evaluated": False}
    )
    assert failed_permanently is False
    assert qc_dict is None


def test_build_concept_plan_from_graph() -> None:
    plan = _build_concept_plan_from_graph(
        {
            "domain": "Programming",
            "topic_split": [{"section_id": "s1"}],
            "must_cover_checklist": [{"id": "c1"}],
        }
    )
    assert plan == {
        "domain": "Programming",
        "topic_split": [{"section_id": "s1"}],
        "must_cover_checklist": [{"id": "c1"}],
    }


def test_hydration_from_active_version_uses_concept_plan() -> None:
    active = SimpleNamespace(
        concept_plan={
            "domain": "STEM",
            "topic_split": [{"section_id": "intro"}],
            "must_cover_checklist": [{"id": "c1", "concept": "variables"}],
        },
        checklist_llm_model_used="llama-3.3-70b-versatile",
        qc_frozen_check_ids=["c1"],
        qc_frozen_section_keys=["intro"],
        qc_result={
            "overall_status": "warn",
            "checks": [
                {
                    "id": "x1",
                    "category": "content_accuracy",
                    "question": "q",
                    "passed": False,
                    "severity": "major",
                    "evidence": "missing detail",
                    "corrective_hint": "add detail",
                }
            ],
        },
    )

    hydration, failed_feedback = _hydration_from_active_version(active)

    assert hydration["domain"] == "STEM"
    assert hydration["must_cover_checklist"] == [{"id": "c1", "concept": "variables"}]
    assert hydration["qc_frozen_check_ids"] == ["c1"]
    assert hydration["qc_frozen_section_keys"] == ["intro"]
    assert failed_feedback is not None
    assert "content_accuracy" in failed_feedback


@pytest.mark.asyncio
async def test_create_version_persists_qc_generation_fields() -> None:
    session = MagicMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    session.flush = AsyncMock()

    repo = StudyMaterialRepository(session)
    node_id = uuid4()
    space_id = uuid4()
    user_id = uuid4()
    retry_at = datetime(2026, 6, 26, 12, 0, tzinfo=UTC)
    concept_plan = {
        "domain": "Programming",
        "topic_split": [{"id": "ts_1"}],
        "must_cover_checklist": [{"id": "c1", "concept": "loops"}],
    }
    qc_result = {"overall_status": "pass", "scores": {"content_accuracy": 9}}

    version = await repo.create_version(
        node_id=node_id,
        space_id=space_id,
        version_number=1,
        content='{"sections": []}',
        generation_type="generate",
        mentor_feedback_used=None,
        reference_material_id=None,
        based_on_version_id=None,
        llm_model_used="llama-3.3-70b-versatile",
        prompt_snapshot=None,
        token_usage=100,
        is_active=True,
        created_by=user_id,
        qc_passed=True,
        qc_attempt_count=2,
        generation_run_id="run_20260626_120000",
        concept_plan=concept_plan,
        checklist_llm_model_used="llama-3.3-70b-versatile",
        qc_verification_mode="targeted",
        qc_frozen_check_ids=["c1"],
        qc_frozen_section_keys=["ts_1"],
        qc_result=qc_result,
        next_llm_retry_at=retry_at,
        commit=False,
    )

    session.add.assert_called_once()
    added = session.add.call_args[0][0]
    assert added.qc_passed is True
    assert added.qc_attempt_count == 2
    assert added.generation_run_id == "run_20260626_120000"
    assert added.concept_plan == concept_plan
    assert added.checklist_llm_model_used == "llama-3.3-70b-versatile"
    assert added.qc_verification_mode == "targeted"
    assert added.qc_frozen_check_ids == ["c1"]
    assert added.qc_frozen_section_keys == ["ts_1"]
    assert added.qc_result == qc_result
    assert added.next_llm_retry_at == retry_at
    assert version.qc_passed is True


def test_create_version_persists_generation_outcome_fields() -> None:
    session = MagicMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    session.flush = AsyncMock()

    repo = StudyMaterialRepository(session)
    node_id = uuid4()
    space_id = uuid4()
    user_id = uuid4()
    outcome_detail = {
        "message": "Upload a PDF.",
        "topic_received": "Rust",
    }

    async def _run() -> None:
        version = await repo.create_version(
            node_id=node_id,
            space_id=space_id,
            version_number=1,
            content="GENERATION STATUS: Reference material required",
            generation_type="generate",
            mentor_feedback_used=None,
            reference_material_id=None,
            based_on_version_id=None,
            llm_model_used="llama-3.3-70b-versatile",
            prompt_snapshot=None,
            token_usage=100,
            is_active=True,
            created_by=user_id,
            generation_outcome="reference_required",
            generation_outcome_detail=outcome_detail,
            qc_evaluated=False,
            commit=False,
        )
        session.add.assert_called_once()
        added = session.add.call_args[0][0]
        assert added.generation_outcome == "reference_required"
        assert added.generation_outcome_detail == outcome_detail
        assert added.qc_evaluated is False
        assert version.generation_outcome == "reference_required"

    asyncio.run(_run())


def test_study_material_version_out_attaches_action_required() -> None:
    version = SimpleNamespace(
        version_id=uuid4(),
        node_id=uuid4(),
        space_id=uuid4(),
        version_number=1,
        content="GENERATION STATUS: Reference material required",
        generation_type="generate",
        mentor_feedback_used=None,
        reference_material_id=None,
        based_on_version_id=None,
        llm_model_used=None,
        prompt_snapshot=None,
        token_usage=None,
        is_active=True,
        is_published=False,
        is_archived=False,
        archived_at=None,
        published_at=None,
        published_by=None,
        created_by=uuid4(),
        created_at=datetime(2026, 6, 26, 12, 0, tzinfo=UTC),
        qc_failed_permanently=False,
        qc_result=None,
        qc_passed=False,
        qc_attempt_count=0,
        generation_run_id=None,
        concept_plan=None,
        checklist_llm_model_used=None,
        qc_verification_mode=None,
        qc_frozen_check_ids=None,
        qc_frozen_section_keys=None,
        next_llm_retry_at=None,
        generation_outcome="reference_required",
        generation_outcome_detail={
            "message": "Upload official docs.",
            "topic_received": "Quantum",
        },
        qc_evaluated=False,
    )

    out = _study_material_version_out(version)

    assert out.generation_outcome == "reference_required"
    assert out.qc_evaluated is False
    assert out.action_required is not None
    assert out.action_required.type == "upload_reference"
    assert out.action_required.topic_received == "Quantum"


@pytest.mark.asyncio
async def test_concept_checklist_skips_llm_when_plan_hydrated_on_generate() -> None:
    state = {
        "node_id": uuid4(),
        "generation_mode": "generate",
        "must_cover_checklist": [{"id": "c1", "concept": "loops"}],
        "topic_split": [{"section_id": "s1"}],
        "domain": "Programming",
        "checklist_llm_model_used": "llama-3.1-8b-instant",
    }

    with patch(
        "src.api.control.study_agent.nodes.concept_checklist_node.call_groq_with_rotation",
        new_callable=AsyncMock,
    ) as mock_llm:
        result = await concept_checklist_node(state, config={})

    mock_llm.assert_not_called()
    assert result["must_cover_checklist"] == [{"id": "c1", "concept": "loops"}]
    assert result["domain"] == "Programming"
    assert result["checklist_llm_model_used"] == "llama-3.1-8b-instant"


@pytest.mark.asyncio
async def test_concept_checklist_regenerates_on_improve_even_when_plan_hydrated() -> (
    None
):
    state = {
        "node_id": uuid4(),
        "generation_mode": "improve",
        "node_title": "Concurrency",
        "effective_instruction": "Teach concurrency basics.",
        "mentor_feedback": "Remove all coding examples; theory only.",
        "must_cover_checklist": [
            {
                "id": "mc_1",
                "concept": "Semaphores",
                "requirement": "Show semaphore code.",
                "priority": "required",
                "section_id": "ts_1",
                "depth_gate": "Runnable code example provided.",
            }
        ],
        "topic_split": [{"id": "ts_1", "heading": "Sync", "purpose": "Learn sync."}],
        "domain": "Programming",
    }
    llm_payload = json.dumps(
        {
            "domain": "Conceptual",
            "topic_split": [
                {
                    "id": "ts_1",
                    "heading": "Synchronization",
                    "purpose": "Explain synchronization without code.",
                }
            ],
            "must_cover_checklist": [
                {
                    "id": "mc_1",
                    "concept": "Semaphores",
                    "requirement": "Explain semaphore wait/signal in prose.",
                    "priority": "required",
                    "section_id": "ts_1",
                    "depth_gate": "Mechanism described with a named OS example; no code required.",
                }
            ],
        }
    )

    with patch(
        "src.api.control.study_agent.nodes.concept_checklist_node.call_groq_with_rotation",
        new_callable=AsyncMock,
        return_value=SimpleNamespace(
            ok=True,
            content=llm_payload,
            model="llama-3.1-8b-instant",
            error_type=None,
        ),
    ) as mock_llm:
        result = await concept_checklist_node(state, config={})

    mock_llm.assert_called_once()
    user_message = mock_llm.call_args.kwargs["messages"][1].content
    assert "<mentor_feedback>" in user_message
    assert "Remove all coding examples" in user_message
    assert "<previous_plan>" in user_message
    assert result["domain"] == "Conceptual"
    assert result["must_cover_checklist"][0]["depth_gate"].startswith(
        "Mechanism described"
    )


@pytest.mark.asyncio
async def test_concept_checklist_returns_terminal_failure_on_groq_error() -> None:
    state = {
        "node_id": uuid4(),
        "node_title": "Integrals",
        "generation_mode": "generate",
        "effective_instruction": "Cover integration fundamentals.",
        "artifact_run_id": "20260626_test",
    }
    retry_at = datetime(2026, 6, 26, 16, 0, 0, tzinfo=UTC)

    with patch(
        "src.api.control.study_agent.nodes.concept_checklist_node.call_groq_with_rotation",
        new_callable=AsyncMock,
        return_value=SimpleNamespace(
            ok=False,
            content=None,
            model="llama-3.1-8b-instant",
            error_type="rate_limited",
            provider_meta={"api_key_alias": "key_1", "attempt_index": 1},
            retry_after_seconds=60,
            next_llm_retry_at=retry_at,
            suggestion=None,
        ),
    ) as mock_llm:
        result = await concept_checklist_node(state, config={})

    mock_llm.assert_called_once()
    assert result["terminal_llm_failure"] is True
    assert result["llm_error_type"] == "rate_limited"
    assert result["next_llm_retry_at"] == retry_at
    assert result["qc_failed_permanently"] is True
    assert result["qc_result"]["errorType"] == "rate_limited"
    assert "must_cover_checklist" not in result
