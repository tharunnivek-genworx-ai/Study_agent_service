"""Pipeline step definitions and node-to-step mapping for generation progress."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from src.api.schemas import (
    GenerationPipeline,
    GenerationProgressStep,
    GenerationProgressStepDef,
    GenerationStepStatus,
)


class GenerationStepProfile(StrEnum):
    STUDY_GENERATE_WITH_REF = "study_generate_with_ref"
    STUDY_GENERATE_NO_REF = "study_generate_no_ref"
    STUDY_GENERATE_WITH_EXTERNAL_RESEARCH = "study_generate_with_external_research"
    STUDY_FEEDBACK_REWORK = "study_feedback_rework"
    QUIZ_GENERATE = "quiz_generate"
    QUIZ_REGENERATE = "quiz_regenerate"
    QUIZ_QUESTION_REWORK = "quiz_question_rework"
    HINT_GENERATE = "hint_generate"
    HINT_REGENERATE = "hint_regenerate"


_STEP_PROFILE_DEFS: dict[GenerationStepProfile, list[GenerationProgressStepDef]] = {
    GenerationStepProfile.STUDY_GENERATE_WITH_REF: [
        GenerationProgressStepDef(
            id="outlining", label="Outlining the topics to cover"
        ),
        GenerationProgressStepDef(
            id="reading_reference", label="Reading the reference material"
        ),
        GenerationProgressStepDef(id="generating", label="Generating study material"),
        GenerationProgressStepDef(
            id="assessing", label="Assessing the quality of the content"
        ),
    ],
    GenerationStepProfile.STUDY_GENERATE_NO_REF: [
        GenerationProgressStepDef(
            id="outlining", label="Outlining the topics to cover"
        ),
        GenerationProgressStepDef(id="generating", label="Generating study material"),
        GenerationProgressStepDef(
            id="assessing", label="Assessing the quality of the content"
        ),
    ],
    GenerationStepProfile.STUDY_GENERATE_WITH_EXTERNAL_RESEARCH: [
        GenerationProgressStepDef(
            id="outlining", label="Outlining the topics to cover"
        ),
        GenerationProgressStepDef(
            id="researching", label="Researching external sources"
        ),
        GenerationProgressStepDef(id="generating", label="Generating study material"),
        GenerationProgressStepDef(
            id="assessing", label="Assessing the quality of the content"
        ),
    ],
    GenerationStepProfile.STUDY_FEEDBACK_REWORK: [
        GenerationProgressStepDef(
            id="outlining", label="Outlining the topics to cover"
        ),
        GenerationProgressStepDef(id="generating", label="Generating study material"),
        GenerationProgressStepDef(
            id="assessing", label="Assessing the quality of the content"
        ),
    ],
    GenerationStepProfile.QUIZ_GENERATE: [
        GenerationProgressStepDef(
            id="outlining", label="Outlining the topics to cover"
        ),
        GenerationProgressStepDef(id="generating", label="Generating quiz"),
        GenerationProgressStepDef(
            id="assessing", label="Assessing the quality of the content"
        ),
    ],
    GenerationStepProfile.QUIZ_REGENERATE: [
        GenerationProgressStepDef(
            id="outlining", label="Outlining the topics to cover"
        ),
        GenerationProgressStepDef(id="generating", label="Generating quiz"),
        GenerationProgressStepDef(
            id="assessing", label="Assessing the quality of the content"
        ),
    ],
    GenerationStepProfile.QUIZ_QUESTION_REWORK: [
        GenerationProgressStepDef(
            id="preparing_question", label="Preparing question rework"
        ),
        GenerationProgressStepDef(id="regenerating", label="Regenerating question"),
        GenerationProgressStepDef(id="validating", label="Validating question quality"),
        GenerationProgressStepDef(id="saving", label="Saving changes"),
    ],
    GenerationStepProfile.HINT_GENERATE: [
        GenerationProgressStepDef(id="generating", label="Generating hints"),
        GenerationProgressStepDef(id="validating", label="Validating hint quality"),
        GenerationProgressStepDef(id="saving", label="Saving hints"),
    ],
    GenerationStepProfile.HINT_REGENERATE: [
        GenerationProgressStepDef(id="generating", label="Generating hints"),
        GenerationProgressStepDef(id="validating", label="Validating hint quality"),
        GenerationProgressStepDef(id="saving", label="Saving hints"),
    ],
}

# Study material: resolver is invisible; outlining starts at concept_checklist.
_STUDY_WITH_REF_NODES: dict[str, int] = {
    "concept_checklist": 0,
    "llamaparse": 1,
    "study_agent": 2,
    "quality_check": 3,
}

_STUDY_NO_REF_NODES: dict[str, int] = {
    "concept_checklist": 0,
    "study_agent": 1,
    "quality_check": 2,
}

# Parent + every internal research node map to the researching step (index 1).
_STUDY_WITH_EXTERNAL_RESEARCH_NODES: dict[str, int] = {
    "concept_checklist": 0,
    "reference_router": 0,
    "external_research": 1,
    "external_research_cache_check": 1,
    "external_research_resolve_query": 1,
    "external_research_search": 1,
    "external_research_content_extraction": 1,
    "external_research_content_distillation": 1,
    "external_research_chunk_if_needed": 1,
    "external_research_knowledge_distillation": 1,
    "external_research_website_reduction": 1,
    "external_research_cross_website_merge": 1,
    "external_research_persist_cache": 1,
    "external_research_attach_sources": 1,
    "study_agent": 2,
    "quality_check": 3,
}

_QUIZ_FULL_NODES: dict[str, int] = {
    "load_generation_context": 0,
    "load_existing_quiz_if_regenerate": 0,
    "quiz_generator": 1,
    "parse_quiz_output": 1,
    "deterministic_validate": 1,
    "quality_check": 2,
    "persist_quiz_draft": 2,
}

_QUIZ_QUESTION_REWORK_NODES: dict[str, int] = {
    "load_quiz_single_regen_context": 0,
    "build_quiz_single_regen_prompt": 0,
    "invoke_quiz_single_regen_llm": 1,
    "parse_quiz_single_regen_output": 1,
    "deterministic_validate_question_patches": 2,
    "persist_question_patches": 3,
}

_HINT_NODES: dict[str, int] = {
    "load_hint_context": 0,
    "build_hint_prompt_payload": 0,
    "invoke_hint_llm": 0,
    "parse_hint_output": 0,
    "validate_hint_quality": 1,
    "persist_hints_to_questions": 2,
    "persist_hint_failure_diagnostics": 2,
}

_PROFILE_NODE_MAP: dict[GenerationStepProfile, dict[str, int]] = {
    GenerationStepProfile.STUDY_GENERATE_WITH_REF: _STUDY_WITH_REF_NODES,
    GenerationStepProfile.STUDY_GENERATE_NO_REF: _STUDY_NO_REF_NODES,
    GenerationStepProfile.STUDY_GENERATE_WITH_EXTERNAL_RESEARCH: (
        _STUDY_WITH_EXTERNAL_RESEARCH_NODES
    ),
    GenerationStepProfile.STUDY_FEEDBACK_REWORK: _STUDY_NO_REF_NODES,
    GenerationStepProfile.QUIZ_GENERATE: _QUIZ_FULL_NODES,
    GenerationStepProfile.QUIZ_REGENERATE: _QUIZ_FULL_NODES,
    GenerationStepProfile.QUIZ_QUESTION_REWORK: _QUIZ_QUESTION_REWORK_NODES,
    GenerationStepProfile.HINT_GENERATE: _HINT_NODES,
    GenerationStepProfile.HINT_REGENERATE: _HINT_NODES,
}

_DEFAULT_PROFILE_BY_PIPELINE: dict[GenerationPipeline, GenerationStepProfile] = {
    GenerationPipeline.STUDY_MATERIAL: GenerationStepProfile.STUDY_GENERATE_NO_REF,
    GenerationPipeline.QUIZ: GenerationStepProfile.QUIZ_GENERATE,
    GenerationPipeline.HINT: GenerationStepProfile.HINT_GENERATE,
}


def step_profile_from_request_params(
    request_params: dict[str, Any] | None,
    *,
    pipeline: GenerationPipeline,
) -> GenerationStepProfile:
    """Resolve step profile from run request_params, with pipeline fallback."""
    if request_params:
        raw = request_params.get("step_profile")
        if raw is not None:
            try:
                return GenerationStepProfile(str(raw))
            except ValueError:
                pass
    return _DEFAULT_PROFILE_BY_PIPELINE[pipeline]


def step_defs_for_profile(
    profile: GenerationStepProfile,
) -> list[GenerationProgressStepDef]:
    return _STEP_PROFILE_DEFS[profile]


def step_defs(pipeline: GenerationPipeline) -> list[GenerationProgressStepDef]:
    """Legacy helper — uses default profile for the pipeline."""
    return step_defs_for_profile(_DEFAULT_PROFILE_BY_PIPELINE[pipeline])


def build_steps_for_profile(
    profile: GenerationStepProfile, active_index: int
) -> list[GenerationProgressStep]:
    rendered: list[GenerationProgressStep] = []
    for index, step in enumerate(step_defs_for_profile(profile)):
        if index < active_index:
            status = GenerationStepStatus.COMPLETED
        elif index == active_index:
            status = GenerationStepStatus.ACTIVE
        else:
            status = GenerationStepStatus.PENDING
        rendered.append(
            GenerationProgressStep(
                id=step.id,
                label=step.label,
                status=status,
            )
        )
    return rendered


def build_steps(
    pipeline: GenerationPipeline, active_index: int
) -> list[GenerationProgressStep]:
    return build_steps_for_profile(_DEFAULT_PROFILE_BY_PIPELINE[pipeline], active_index)


def node_to_step_for_profile(
    profile: GenerationStepProfile, node_name: str
) -> int | None:
    return _PROFILE_NODE_MAP.get(profile, {}).get(node_name)


def node_to_step(
    pipeline: GenerationPipeline,
    node_name: str,
    *,
    step_profile: GenerationStepProfile | None = None,
) -> int | None:
    profile = step_profile or _DEFAULT_PROFILE_BY_PIPELINE[pipeline]
    return node_to_step_for_profile(profile, node_name)


def study_step_profile_for_mode(
    *,
    generation_mode: str,
    has_reference_material: bool,
    external_research_enabled: bool = False,
) -> GenerationStepProfile:
    if generation_mode in ("regenerate", "improve"):
        return GenerationStepProfile.STUDY_FEEDBACK_REWORK
    if external_research_enabled:
        return GenerationStepProfile.STUDY_GENERATE_WITH_EXTERNAL_RESEARCH
    if has_reference_material:
        return GenerationStepProfile.STUDY_GENERATE_WITH_REF
    return GenerationStepProfile.STUDY_GENERATE_NO_REF


def quiz_step_profile_for_mode(
    *,
    generation_mode: str,
    is_question_rework: bool = False,
) -> GenerationStepProfile:
    if is_question_rework:
        return GenerationStepProfile.QUIZ_QUESTION_REWORK
    if generation_mode == "regenerate":
        return GenerationStepProfile.QUIZ_REGENERATE
    return GenerationStepProfile.QUIZ_GENERATE


def hint_step_profile_for_mode(*, generation_mode: str) -> GenerationStepProfile:
    if generation_mode == "regenerate":
        return GenerationStepProfile.HINT_REGENERATE
    return GenerationStepProfile.HINT_GENERATE
