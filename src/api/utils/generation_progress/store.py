"""Pipeline step definitions and node-to-step mapping for generation progress."""

from __future__ import annotations

from src.api.schemas import (
    GenerationPipeline,
    GenerationProgressStep,
    GenerationProgressStepDef,
    GenerationStepStatus,
)

STUDY_MATERIAL_STEP_DEFS: list[GenerationProgressStepDef] = [
    GenerationProgressStepDef(id="preparing", label="Preparing materials"),
    GenerationProgressStepDef(id="outlining", label="Outlining the topics to cover"),
    GenerationProgressStepDef(id="generating", label="Generating study material"),
    GenerationProgressStepDef(
        id="analyzing", label="Analyzing the quality of the content"
    ),
]

QUIZ_STEP_DEFS: list[GenerationProgressStepDef] = [
    GenerationProgressStepDef(id="preparing", label="Preparing materials"),
    GenerationProgressStepDef(id="outlining", label="Outlining the topics to cover"),
    GenerationProgressStepDef(id="generating", label="Generating quiz"),
    GenerationProgressStepDef(
        id="analyzing", label="Analyzing the quality of the content"
    ),
]

STUDY_MATERIAL_NODE_TO_STEP: dict[str, int] = {
    "resolver": 0,
    "llamaparse": 0,
    "concept_checklist": 1,
    "study_agent": 2,
    "quality_check": 3,
}

QUIZ_NODE_TO_STEP: dict[str, int] = {
    "load_generation_context": 0,
    "load_existing_quiz_if_regenerate": 0,
    "load_quiz_single_regen_context": 0,
    "build_quiz_single_regen_prompt": 0,
    "quiz_generator": 2,
    "parse_quiz_output": 2,
    "deterministic_validate": 2,
    "invoke_quiz_single_regen_llm": 2,
    "parse_quiz_single_regen_output": 2,
    "deterministic_validate_question_patches": 3,
    "quality_check": 3,
    "persist_quiz_draft": 3,
    "persist_question_patches": 3,
}

QUIZ_CONTEXT_LOAD_NODES = frozenset(
    {
        "load_generation_context",
        "load_existing_quiz_if_regenerate",
        "load_quiz_single_regen_context",
        "build_quiz_single_regen_prompt",
    }
)

HINT_STEP_DEFS: list[GenerationProgressStepDef] = [
    GenerationProgressStepDef(id="preparing", label="Preparing materials"),
    GenerationProgressStepDef(id="generating", label="Generating hints"),
    GenerationProgressStepDef(id="validating", label="Validating hint quality"),
    GenerationProgressStepDef(id="saving", label="Saving hints"),
]

HINT_NODE_TO_STEP: dict[str, int] = {
    "load_hint_context": 0,
    "build_hint_prompt_payload": 0,
    "invoke_hint_llm": 1,
    "parse_hint_output": 1,
    "validate_hint_quality": 2,
    "persist_hints_to_questions": 3,
    "persist_hint_failure_diagnostics": 3,
}


def step_defs(pipeline: GenerationPipeline) -> list[GenerationProgressStepDef]:
    if pipeline == GenerationPipeline.QUIZ:
        return QUIZ_STEP_DEFS
    if pipeline == GenerationPipeline.HINT:
        return HINT_STEP_DEFS
    return STUDY_MATERIAL_STEP_DEFS


def build_steps(
    pipeline: GenerationPipeline, active_index: int
) -> list[GenerationProgressStep]:
    rendered: list[GenerationProgressStep] = []
    for index, step in enumerate(step_defs(pipeline)):
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


def node_to_step(pipeline: GenerationPipeline, node_name: str) -> int | None:
    if pipeline == GenerationPipeline.QUIZ:
        if node_name in QUIZ_CONTEXT_LOAD_NODES:
            return 1
        return QUIZ_NODE_TO_STEP.get(node_name)
    if pipeline == GenerationPipeline.HINT:
        return HINT_NODE_TO_STEP.get(node_name)
    return STUDY_MATERIAL_NODE_TO_STEP.get(node_name)
