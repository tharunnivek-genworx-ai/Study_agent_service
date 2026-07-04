"""Shared types for prompt test runners."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from src.api.schemas.qc_schemas.qc_retry_routing_schema import RetryRoutingResult


@dataclass
class PromptTestInputs:
    topic: str
    effective_instruction: str


@dataclass
class ChecklistRunResult:
    ok: bool
    output_dir: Path
    domain: str = ""
    topic_split: list[dict[str, Any]] = field(default_factory=list)
    must_cover_checklist: list[dict[str, Any]] = field(default_factory=list)
    raw_response: str | None = None
    parsed_plan: dict[str, Any] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


@dataclass
class GenerationRunResult:
    ok: bool
    output_dir: Path
    generated_content: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


@dataclass
class QCRunResult:
    ok: bool
    output_dir: Path
    attempt: int = 1
    qc_passed: bool = False
    qc_failed_permanently: bool = False
    qc_result: dict[str, Any] | None = None
    routing: RetryRoutingResult | None = None
    qc_feedback: str = ""
    verification_mode: str | None = None
    frozen_check_ids: list[str] | None = None
    frozen_section_ids: list[str] | None = None
    section_content_hashes: dict[str, str] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


@dataclass
class RetryRunResult:
    ok: bool
    output_dir: Path
    retry_mode: str
    attempt: int
    generated_content: str | None = None
    fixed_sections: list[dict[str, Any]] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


@dataclass
class PromptTestRun:
    run_dir: Path
    topic_slug: str
    timestamp: str
    started_at: datetime
    inputs: PromptTestInputs
    checklist: ChecklistRunResult | None = None
    generation: GenerationRunResult | None = None
    qc_attempts: list[QCRunResult] = field(default_factory=list)
    retries: list[RetryRunResult] = field(default_factory=list)
    final_qc_passed: bool = False
    final_status: str = "unknown"
