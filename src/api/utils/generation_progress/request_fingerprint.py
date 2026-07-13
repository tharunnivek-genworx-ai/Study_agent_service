"""Canonical request fingerprint for generation run resume validation."""

from __future__ import annotations

import hashlib
import json
from typing import Any
from uuid import UUID

from src.api.schemas import GenerationRunCreate, GenerationRunPipeline


def _stable_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


def _hash_fields(fields: dict[str, Any]) -> str:
    return hashlib.sha256(_stable_json(fields).encode("utf-8")).hexdigest()


def _instruction_fingerprint(request_params: dict[str, Any]) -> str | None:
    for key in (
        "instruction_hash",
        "effective_instruction",
        "mentor_feedback",
        "mentor_regeneration_goal",
    ):
        value = request_params.get(key)
        if value is not None and str(value).strip():
            return str(value)
    return None


def _study_material_fields(
    *,
    node_id: UUID,
    generation_mode: str,
    request_params: dict[str, Any],
) -> dict[str, Any]:
    instruction = _instruction_fingerprint(request_params)
    fields: dict[str, Any] = {
        "pipeline": GenerationRunPipeline.STUDY_MATERIAL.value,
        "node_id": str(node_id),
        "generation_mode": generation_mode,
        "reference_material_id": request_params.get("reference_material_id"),
        "based_on_version_id": request_params.get("based_on_version_id"),
    }
    if instruction is not None:
        fields["instruction"] = instruction
    return fields


def _quiz_fields(
    *,
    generation_mode: str,
    request_params: dict[str, Any],
) -> dict[str, Any]:
    question_ids = request_params.get("question_ids")
    if question_ids is not None:
        question_ids = sorted(str(qid) for qid in question_ids)
    return {
        "pipeline": GenerationRunPipeline.QUIZ.value,
        "generation_mode": generation_mode,
        "quiz_id": request_params.get("quiz_id"),
        "mode": request_params.get("mode"),
        "question_count": request_params.get("question_count"),
        "difficulty": request_params.get("difficulty"),
        "mentor_feedback": request_params.get("mentor_feedback"),
        "study_material_version_id": request_params.get("study_material_version_id"),
        "failed_qc_feedback": request_params.get("failed_qc_feedback"),
        "title": request_params.get("title"),
        "question_ids": question_ids,
    }


def _hint_fields(
    *,
    generation_mode: str,
    request_params: dict[str, Any],
) -> dict[str, Any]:
    question_ids = request_params.get("questions_filter_ids")
    if question_ids is not None:
        question_ids = sorted(str(qid) for qid in question_ids)
    return {
        "pipeline": GenerationRunPipeline.HINT.value,
        "generation_mode": generation_mode,
        "quiz_id": request_params.get("quiz_id"),
        "scope": request_params.get("scope"),
        "questions_filter_ids": question_ids,
        "mentor_feedback": request_params.get("mentor_feedback"),
    }


def compute_request_fingerprint(payload: GenerationRunCreate) -> str:
    """SHA-256 fingerprint of stable inputs for a new generation run."""
    params = payload.request_params or {}
    mode = payload.generation_mode.value

    if payload.pipeline == GenerationRunPipeline.STUDY_MATERIAL:
        fields = _study_material_fields(
            node_id=payload.node_id,
            generation_mode=mode,
            request_params=params,
        )
    elif payload.pipeline == GenerationRunPipeline.QUIZ:
        fields = _quiz_fields(generation_mode=mode, request_params=params)
    elif payload.pipeline == GenerationRunPipeline.HINT:
        fields = _hint_fields(generation_mode=mode, request_params=params)
    else:
        fields = {
            "pipeline": payload.pipeline.value,
            "generation_mode": mode,
            "resource_id": str(payload.resource_id),
            "node_id": str(payload.node_id),
        }

    return _hash_fields(fields)


def compute_request_fingerprint_from_run(
    *,
    pipeline: str,
    node_id: UUID,
    generation_mode: str,
    request_params: dict[str, Any] | None,
) -> str:
    """Recompute fingerprint from persisted run attributes."""
    params = request_params or {}
    if pipeline == GenerationRunPipeline.STUDY_MATERIAL.value:
        fields = _study_material_fields(
            node_id=node_id,
            generation_mode=generation_mode,
            request_params=params,
        )
    elif pipeline == GenerationRunPipeline.QUIZ.value:
        fields = _quiz_fields(generation_mode=generation_mode, request_params=params)
    elif pipeline == GenerationRunPipeline.HINT.value:
        fields = _hint_fields(generation_mode=generation_mode, request_params=params)
    else:
        fields = {
            "pipeline": pipeline,
            "generation_mode": generation_mode,
            "node_id": str(node_id),
        }
    return _hash_fields(fields)


def fingerprints_match(
    stored_fingerprint: str | None,
    *,
    pipeline: str,
    node_id: UUID,
    generation_mode: str,
    request_params: dict[str, Any] | None,
) -> bool:
    """Return True when stored and recomputed fingerprints align."""
    if not stored_fingerprint:
        return True
    recomputed = compute_request_fingerprint_from_run(
        pipeline=pipeline,
        node_id=node_id,
        generation_mode=generation_mode,
        request_params=request_params,
    )
    return stored_fingerprint == recomputed
