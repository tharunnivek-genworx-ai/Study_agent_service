"""Tests for generation step profiles and node-to-step mapping."""

from __future__ import annotations

from src.api.schemas import GenerationPipeline
from src.api.schemas.common import GenerationJobStatus
from src.api.utils.generation_progress.store import (
    GenerationStepProfile,
    build_steps_for_profile,
    hint_step_profile_for_mode,
    node_to_step_for_profile,
    quiz_step_profile_for_mode,
    step_defs_for_profile,
    step_profile_from_request_params,
    study_step_profile_for_mode,
)


def test_study_generate_with_ref_step_order() -> None:
    steps = step_defs_for_profile(GenerationStepProfile.STUDY_GENERATE_WITH_REF)
    labels = [step.label for step in steps]
    assert labels == [
        "Outlining the topics to cover",
        "Reading the reference material",
        "Generating study material",
        "Assessing the quality of the content",
    ]


def test_study_generate_no_ref_omits_reading_step() -> None:
    steps = step_defs_for_profile(GenerationStepProfile.STUDY_GENERATE_NO_REF)
    ids = [step.id for step in steps]
    assert ids == ["outlining", "generating", "assessing"]
    assert "reading_reference" not in ids


def test_no_global_preparing_materials_step_in_any_profile() -> None:
    for profile in GenerationStepProfile:
        for step in step_defs_for_profile(profile):
            assert step.label != "Preparing materials"


def test_study_step_profile_for_mode_with_reference() -> None:
    profile = study_step_profile_for_mode(
        generation_mode="generate",
        has_reference_material=True,
    )
    assert profile == GenerationStepProfile.STUDY_GENERATE_WITH_REF


def test_study_step_profile_for_feedback_rework() -> None:
    profile = study_step_profile_for_mode(
        generation_mode="improve",
        has_reference_material=True,
    )
    assert profile == GenerationStepProfile.STUDY_FEEDBACK_REWORK


def test_quiz_question_rework_profile() -> None:
    profile = quiz_step_profile_for_mode(
        generation_mode="regenerate",
        is_question_rework=True,
    )
    assert profile == GenerationStepProfile.QUIZ_QUESTION_REWORK


def test_hint_regenerate_profile() -> None:
    assert (
        hint_step_profile_for_mode(generation_mode="regenerate")
        == GenerationStepProfile.HINT_REGENERATE
    )


def test_step_profile_from_request_params() -> None:
    profile = step_profile_from_request_params(
        {"step_profile": "study_generate_with_ref"},
        pipeline=GenerationPipeline.STUDY_MATERIAL,
    )
    assert profile == GenerationStepProfile.STUDY_GENERATE_WITH_REF


def test_node_to_step_for_study_with_ref() -> None:
    profile = GenerationStepProfile.STUDY_GENERATE_WITH_REF
    assert node_to_step_for_profile(profile, "concept_checklist") == 0
    assert node_to_step_for_profile(profile, "llamaparse") == 1
    assert node_to_step_for_profile(profile, "study_agent") == 2
    assert node_to_step_for_profile(profile, "quality_check") == 3
    assert node_to_step_for_profile(profile, "resolver") is None


def test_build_steps_for_profile_marks_active_index() -> None:
    steps = build_steps_for_profile(
        GenerationStepProfile.STUDY_GENERATE_NO_REF,
        active_index=1,
    )
    assert [step.status.value for step in steps] == [
        "completed",
        "active",
        "pending",
    ]


def test_terminal_run_maps_to_failed_progress_status() -> None:
    from src.api.utils.generation_progress.db_store import _status_from_run

    assert _status_from_run("abandoned") == GenerationJobStatus.FAILED
    assert _status_from_run("superseded") == GenerationJobStatus.FAILED
