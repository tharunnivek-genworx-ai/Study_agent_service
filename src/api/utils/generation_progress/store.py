"""In-memory generation progress tracking for long-running agent pipelines."""

from __future__ import annotations

import time
from threading import Lock

from src.api.schemas.generation_progress_schema import (
    GenerationJobStatus,
    GenerationPipeline,
    GenerationProgressOut,
    GenerationProgressRecord,
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
    "quiz_generator": 2,
    "parse_quiz_output": 2,
    "deterministic_validate": 2,
    "quality_check": 3,
    "persist_quiz_draft": 3,
}

QUIZ_CONTEXT_LOAD_NODES = frozenset(
    {"load_generation_context", "load_existing_quiz_if_regenerate"}
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


class GenerationProgressStore:
    """Thread-safe store for short-lived generation progress sessions."""

    def __init__(self) -> None:
        self._records: dict[str, GenerationProgressRecord] = {}
        self._lock = Lock()

    def _step_defs(
        self, pipeline: GenerationPipeline
    ) -> list[GenerationProgressStepDef]:
        if pipeline == GenerationPipeline.QUIZ:
            return QUIZ_STEP_DEFS
        if pipeline == GenerationPipeline.HINT:
            return HINT_STEP_DEFS
        return STUDY_MATERIAL_STEP_DEFS

    def _build_steps(
        self, pipeline: GenerationPipeline, active_index: int
    ) -> list[GenerationProgressStep]:
        rendered: list[GenerationProgressStep] = []
        for index, step in enumerate(self._step_defs(pipeline)):
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

    def start(self, session_id: str, pipeline: GenerationPipeline) -> None:
        with self._lock:
            self._records[session_id] = GenerationProgressRecord(
                session_id=session_id,
                pipeline=pipeline,
                current_step_index=0,
                steps=self._build_steps(pipeline, 0),
            )

    def set_step(self, session_id: str, step_index: int) -> None:
        with self._lock:
            record = self._records.get(session_id)
            if record is None or record.status != GenerationJobStatus.RUNNING:
                return
            bounded = max(0, min(step_index, len(record.steps) - 1))
            record.current_step_index = bounded
            record.steps = self._build_steps(record.pipeline, bounded)
            record.updated_at = time.time()

    def on_node(
        self, session_id: str, pipeline: GenerationPipeline, node_name: str
    ) -> None:
        if pipeline == GenerationPipeline.QUIZ:
            if node_name in QUIZ_CONTEXT_LOAD_NODES:
                self.set_step(session_id, 1)
                return
            step_index = QUIZ_NODE_TO_STEP.get(node_name)
        elif pipeline == GenerationPipeline.HINT:
            step_index = HINT_NODE_TO_STEP.get(node_name)
        else:
            step_index = STUDY_MATERIAL_NODE_TO_STEP.get(node_name)

        if step_index is not None:
            self.set_step(session_id, step_index)

    def complete(self, session_id: str) -> None:
        with self._lock:
            record = self._records.get(session_id)
            if record is None:
                return
            record.status = GenerationJobStatus.COMPLETED
            record.current_step_index = len(record.steps) - 1
            record.steps = self._build_steps(record.pipeline, len(record.steps))
            for step in record.steps:
                step.status = GenerationStepStatus.COMPLETED
            record.updated_at = time.time()

    def fail(self, session_id: str, error: str) -> None:
        with self._lock:
            record = self._records.get(session_id)
            if record is None:
                return
            record.status = GenerationJobStatus.FAILED
            record.error = error
            record.updated_at = time.time()

    def get(self, session_id: str) -> GenerationProgressRecord | None:
        with self._lock:
            record = self._records.get(session_id)
            if record is None:
                return None
            return record.model_copy(deep=True)

    def to_progress_out(self, session_id: str) -> GenerationProgressOut | None:
        record = self.get(session_id)
        if record is None:
            return None
        return record.to_progress_out()


_store = GenerationProgressStore()


def get_generation_progress_store() -> GenerationProgressStore:
    return _store
