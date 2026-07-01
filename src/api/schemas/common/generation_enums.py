"""Shared generation pipeline, run, and version-type enumerations."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal


class GenerationPipeline(StrEnum):
    """Graph and progress-store pipeline identifiers."""

    STUDY_MATERIAL = "study_material"
    QUIZ = "quiz"
    HINT = "hint"


class GenerationJobStatus(StrEnum):
    """Ephemeral progress-store job status (polling UI)."""

    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class GenerationRunStatus(StrEnum):
    """Durable generation-run row status (DB checkpoints).

    Superset of ``GenerationJobStatus``: includes ``superseded`` and
    ``cancelled`` for run lifecycle management that the progress store
    does not model.
    """

    RUNNING = "running"
    FAILED = "failed"
    COMPLETED = "completed"
    SUPERSEDED = "superseded"
    CANCELLED = "cancelled"


class GenerationRunMode(StrEnum):
    """LLM generation mode for a durable run (excludes manual_edit)."""

    GENERATE = "generate"
    REGENERATE = "regenerate"
    IMPROVE = "improve"


GenerationType = Literal["generate", "regenerate", "improve", "manual_edit"]

GenerationMode = Literal["generate", "regenerate", "improve"]

# Backward-compatible alias used by generation_run_schema consumers.
GenerationRunPipeline = GenerationPipeline
