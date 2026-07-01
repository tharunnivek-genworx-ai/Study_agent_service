"""Tests for quiz QC frozen question accumulation and resume hydration."""

from __future__ import annotations

from uuid import uuid4

from src.api.control.quiz_agent.graph.quiz_graph.resume_router import (
    hydrate_checkpoint_state,
    resolve_resume_next_node,
)
from src.api.utils.quiz_utils.quality_check_utils.core.frozen_questions import (
    accumulate_frozen_question_ids,
)


def test_accumulate_frozen_question_ids_merges_passing_questions() -> None:
    checks = [
        {
            "category": "answer_correctness",
            "question_id": "q1",
            "passed": True,
        },
        {
            "category": "question_quality",
            "question_id": "q1",
            "passed": True,
        },
        {
            "category": "answer_correctness",
            "question_id": "q2",
            "passed": False,
        },
        {
            "category": "question_quality",
            "question_id": "q2",
            "passed": True,
        },
    ]
    frozen = accumulate_frozen_question_ids(checks, ["q0"])
    assert frozen == ["q0", "q1"]


def test_resume_after_qc_question_patch_routes_to_generator_not_context() -> None:
    checkpoint = {
        "node_id": str(uuid4()),
        "mode": "generate",
        "study_material_content": "Python basics.",
        "validated_questions": [
            {"question_id": "q1", "question_text": "Passing Q"},
            {"question_id": "q2", "question_text": "Failing Q"},
        ],
        "qc_attempt": 1,
        "qc_retry_mode": "question_patch",
        "qc_reverify_question_ids": ["q2"],
        "qc_frozen_question_ids": ["q1"],
        "qc_question_failures": [
            {"question_id": "q2", "failures": [{"category": "question_quality"}]}
        ],
    }
    hydrated = hydrate_checkpoint_state(
        checkpoint,
        last_completed_node="quality_check",
    )
    assert (
        resolve_resume_next_node(hydrated, last_completed_node="quality_check")
        == "quiz_generator"
    )
    assert hydrated["qc_frozen_question_ids"] == ["q1"]
    assert hydrated["study_material_content"] == "Python basics."
