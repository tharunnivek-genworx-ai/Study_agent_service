# src/api/core/services/study_agent_services/study_material_service.py
"""
Study material service: business logic for study_material_versions.

Generation flow:
  GENERATE   → access guard → LangGraph → persist vN → deactivate previous active
  REGENERATE → load active draft + mentor goal → LangGraph → persist vN+1
  IMPROVE    → load active draft + mentor feedback → LangGraph → persist vN+1
  MANUAL EDIT → access guard → insert new version row (no LLM)

Publish / unpublish (Option B): SM lifecycle is independent of quiz lifecycle on
the node — publishing or superseding study material does not auto-publish,
unpublish, or retire quizzes.
"""

from datetime import datetime
from typing import Any, cast
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.api.control.study_agent.graph.resume_router import hydrate_checkpoint_state
from src.api.control.study_agent.graph.runner import (
    run_study_material_from_checkpoint,
    run_study_material_generation,
    run_study_material_improve,
    run_study_material_regeneration,
)
from src.api.control.study_agent.utils.instructions.instruction_snapshot import (
    embed_effective_instruction_snapshot,
    extract_effective_instruction_snapshot,
)
from src.api.core.exceptions import GenerationRunAborted
from src.api.core.exceptions.generation_run_exceptions import (
    GenerationRunConflictException,
)
from src.api.core.exceptions.study_material_exceptions.study_material_exceptions import (
    LLMGenerationFailedException,
    StudyMaterialCannotArchiveNonDraftException,
    StudyMaterialCannotArchivePublishedException,
    StudyMaterialCannotUnarchiveTraineeHistoryException,
    StudyMaterialClearDraftsBlockedByQuizException,
    StudyMaterialModificationBlockedReferenceMaterialRequiredException,
    StudyMaterialNoActiveVersionException,
    StudyMaterialNoDraftsException,
    StudyMaterialNotFoundException,
    StudyMaterialPdfGenerationFailedException,
    StudyMaterialPublishBlockedReferenceMaterialRequiredException,
    StudyMaterialPublishBlockedSpaceUnpublishedException,
    StudyMaterialVersionAlreadyArchivedException,
    StudyMaterialVersionAlreadyPublishedException,
    StudyMaterialVersionMismatchException,
    StudyMaterialVersionNotArchivedException,
    StudyMaterialVersionNotPublishedException,
)
from src.api.core.services.generation_run_service import GenerationRunService
from src.api.core.services.study_agent_services.study_material_publish_ops import (
    execute_publish_version_cascade,
    execute_unpublish_version_cascade,
)
from src.api.data.models.postgres.e_learning_content.study_material_versions import (
    StudyMaterialVersion,
)
from src.api.data.repositories.progress_repositories.mentor_progress_repository import (
    MentorProgressRepository,
)
from src.api.data.repositories.space_node_repository.node_repository import (
    NodeRepository,
)
from src.api.data.repositories.study_agent_repositories.study_material_repository import (
    StudyMaterialRepository,
)
from src.api.data.repositories.trainee_quiz_repositories.trainee_quiz_repository import (
    TraineeQuizRepository,
)
from src.api.schemas.common.generation_diagnostics_schema import (
    GenerationDiagnosticsOut,
    QualityCheckItemOut,
)
from src.api.schemas.generation_run_schema import (
    GenerationRunCreate,
    GenerationRunMode,
    GenerationRunPipeline,
    GenerationRunResumeResult,
    GenerationRunStatus,
)
from src.api.schemas.qc_schemas.qc_check_schema import parse_qc_check_item
from src.api.schemas.study_material_schemas.study_material_schema import (
    PublishedResourceTopicSummary,
    QualityCheckResultOut,
    QualityCheckScoresOut,
    RepublishChecklistNodeOut,
    RetentionMode,
    SpacePublishedResourcesResponse,
    SpaceRepublishChecklistOut,
    StudyMaterialActivateRequest,
    StudyMaterialClearDraftsEligibilityOut,
    StudyMaterialClearDraftsOut,
    StudyMaterialFeedbackResponse,
    StudyMaterialGenerateRequest,
    StudyMaterialGenerateResponse,
    StudyMaterialImproveRequest,
    StudyMaterialManualEditRequest,
    StudyMaterialMentorUiStateOut,
    StudyMaterialPublishPreviewOut,
    StudyMaterialPublishRequest,
    StudyMaterialRegenerateRequest,
    StudyMaterialUnpublishPreviewOut,
    StudyMaterialUnpublishRequest,
    StudyMaterialVersionHistoryOut,
    StudyMaterialVersionOut,
    StudyMaterialVersionSummary,
)
from src.api.utils.content_lifecycle import (
    count_blocking_quizzes_for_clear_drafts,
    is_discarded,
    is_mentor_accessible_sm,
    is_mentor_discardable_sm,
    is_mentor_openable_sm,
    is_mentor_visible_sm,
    is_trainee_live_sm,
)
from src.api.utils.content_lifecycle.constants import (
    LIFECYCLE_ARCHIVED,
    LIFECYCLE_DRAFT,
)
from src.api.utils.generation_progress.advisory_lock import (
    release_generation_lock,
    require_generation_lock,
)
from src.api.utils.generation_progress.store import study_step_profile_for_mode
from src.api.utils.space_node_utils.build_node import (
    format_effective_instruction,
    resolve_effective_instruction_parts,
)
from src.api.utils.space_node_utils.node_role_assert import (
    _assert_mentor,
    _assert_space_access,
    _get_node_and_assert_space_access,
    _get_space_and_assert_owner,
)
from src.api.utils.study_agent_utils.artifacts.study_material_artifacts import (
    log_study_material_version,
)
from src.api.utils.study_agent_utils.generation.generation_outcome_resolver import (
    resolve_api_generation_outcome,
)
from src.api.utils.study_agent_utils.generation.study_generation_json import (
    build_action_required,
    content_for_persistence,
    parse_generation_document,
)
from src.api.utils.study_agent_utils.media import (
    build_study_material_pdf_filename,
    render_study_material_pdf,
)
from src.api.utils.study_agent_utils.mentor.mentor_student_visibility import (
    build_mentor_student_visibility,
)
from src.api.utils.study_agent_utils.quality_check_utils.core.frozen_sets import (
    effective_frozen_sets,
)
from src.api.utils.study_agent_utils.quality_check_utils.results.feedback import (
    format_qc_feedback,
)
from src.api.utils.study_agent_utils.quality_check_utils.results.scoring import (
    public_scores,
)
from src.api.utils.study_agent_utils.quality_check_utils.results.warning_presentation import (
    enrich_qc_result_for_client,
)
from src.api.utils.study_agent_utils.version.version_actions import (
    compute_version_allowed_actions,
)
from src.api.utils.study_agent_utils.version.version_labels import (
    build_version_display_label,
)


def _request_param_uuid(value: UUID | None) -> str | None:
    return str(value) if value is not None else None


def _clear_drafts_block_reason_no_discardable_versions(
    *,
    versions: list[StudyMaterialVersion],
    blocking_quiz_count: int,
) -> str:
    """Explain why clear-all-drafts is unavailable when nothing is discardable."""
    live_sm_count = sum(1 for v in versions if is_trainee_live_sm(v))
    accessible_count = sum(1 for v in versions if is_mentor_openable_sm(v))
    mentor_archived_count = sum(
        1
        for v in versions
        if v.is_archived and not is_discarded(lifecycle_status=v.lifecycle_status)
    )

    if live_sm_count > 0 and blocking_quiz_count > 0:
        return (
            "Study material and a quiz are live for trainees. "
            "Unpublish both before regenerating from scratch."
        )
    if live_sm_count > 0:
        return (
            "Study material is live for trainees. "
            "Unpublish it before regenerating from scratch."
        )
    if blocking_quiz_count > 0:
        noun = "quiz" if blocking_quiz_count == 1 else "quizzes"
        return (
            f"This topic has {blocking_quiz_count} live or active draft {noun}. "
            "Delete or unpublish them before regenerating from scratch."
        )
    if accessible_count > 0:
        return (
            "There are no unpublished drafts to discard—only live or student-archive "
            "versions remain. Open existing material to edit or improve it."
        )
    if mentor_archived_count > 0:
        return (
            "Your drafts are in the archive. Restore one from the Archive panel, "
            "or use Generate draft to create new material."
        )
    return "No study material has been generated for this topic yet."


def _build_check_items(raw_checks: list[Any] | None) -> list[QualityCheckItemOut]:
    """Map raw check dicts from graph state into typed schema items."""
    if not raw_checks:
        return []
    items: list[QualityCheckItemOut] = []
    for check in raw_checks:
        if not isinstance(check, dict):
            continue
        parsed = parse_qc_check_item(check)
        if parsed is not None:
            items.append(parsed.to_quality_check_item_out())
    return items


def _build_qc_result_out(
    graph_result: dict[str, Any],
) -> QualityCheckResultOut | None:
    """Convert the raw QC dict from graph state into the typed response schema."""
    raw = graph_result.get("qc_result")
    if raw is None or not isinstance(raw, dict):
        return None
    try:
        scores_raw = public_scores(raw.get("scores", {}))
        scores = QualityCheckScoresOut(
            content_accuracy=scores_raw.get("content_accuracy"),
            code_quality=scores_raw.get("code_quality"),
            section_depth=scores_raw.get("section_depth"),
            teaching_alignment=scores_raw.get("teaching_alignment"),
        )
        checks = _build_check_items(raw.get("checks"))
        return QualityCheckResultOut(
            overall_status=raw.get("overall_status", "fail"),
            is_refusal=raw.get("is_refusal", False),
            hallucination_risk=raw.get("hallucination_risk", "none"),
            scores=scores,
            checks=checks,
            issues=raw.get("issues", []),
            corrective_instructions=raw.get("corrective_instructions", ""),
            summary=raw.get("summary", ""),
            must_cover_checklist=(
                graph_result.get("must_cover_checklist")
                or raw.get("must_cover_checklist")
            ),
            qc_llm_model_used=(
                graph_result.get("qc_llm_model_used") or raw.get("qc_llm_model_used")
            ),
            qc_llm_models_used=(
                graph_result.get("qc_llm_models_used") or raw.get("qc_llm_models_used")
            ),
            checklist_llm_model_used=(
                graph_result.get("checklist_llm_model_used")
                or raw.get("checklist_llm_model_used")
            ),
            qc_extraction=(
                graph_result.get("qc_extraction") or raw.get("qc_extraction")
            ),
        )
    except Exception:
        return None


def _enrich_qc_result_dict(
    raw: dict[str, Any],
    graph_result: dict[str, Any],
) -> dict[str, Any]:
    """Attach graph-level QC metadata to the persisted qc_result payload."""
    enriched = dict(raw)
    if graph_result.get("must_cover_checklist") is not None:
        enriched.setdefault(
            "must_cover_checklist", graph_result.get("must_cover_checklist")
        )
    if graph_result.get("qc_llm_model_used"):
        enriched.setdefault("qc_llm_model_used", graph_result.get("qc_llm_model_used"))
    if graph_result.get("qc_llm_models_used"):
        enriched.setdefault(
            "qc_llm_models_used", graph_result.get("qc_llm_models_used")
        )
    if graph_result.get("checklist_llm_model_used"):
        enriched.setdefault(
            "checklist_llm_model_used",
            graph_result.get("checklist_llm_model_used"),
        )
    if graph_result.get("qc_extraction") is not None:
        enriched.setdefault("qc_extraction", graph_result.get("qc_extraction"))
    if graph_result.get("qc_verification_mode"):
        enriched.setdefault(
            "verification_mode", graph_result.get("qc_verification_mode")
        )
    scores = enriched.get("scores")
    if isinstance(scores, dict):
        enriched["scores"] = public_scores(scores)
    concept_plan = _build_concept_plan_from_graph(graph_result)
    return enrich_qc_result_for_client(enriched, concept_plan) or enriched


def _study_material_version_out(
    version: StudyMaterialVersion,
) -> StudyMaterialVersionOut:
    """Build API output with mentor-facing QC warning copy computed server-side."""
    out = StudyMaterialVersionOut.model_validate(version)
    updates: dict[str, Any] = {}

    if isinstance(version.qc_result, dict):
        enriched = enrich_qc_result_for_client(
            version.qc_result,
            version.concept_plan if isinstance(version.concept_plan, dict) else None,
        )
        if enriched:
            try:
                updates["qc_result"] = GenerationDiagnosticsOut.model_validate(enriched)
            except Exception:
                pass

    outcome = version.generation_outcome
    detail = version.generation_outcome_detail
    if outcome:
        action_required = build_action_required(
            outcome,
            detail if isinstance(detail, dict) else None,
        )
        if action_required is not None:
            updates["action_required"] = action_required

    if not updates:
        return out
    return out.model_copy(update=updates)


def _strip_internal_scores_from_qc_dict(qc_dict: dict[str, Any]) -> dict[str, Any]:
    """Remove routing-only score dimensions before API/DB persistence."""
    result = dict(qc_dict)
    scores = result.get("scores")
    if isinstance(scores, dict):
        result["scores"] = public_scores(scores)
    return result


def _build_concept_plan_from_graph(
    graph_result: dict[str, Any],
) -> dict[str, Any] | None:
    """Serialize concept checklist fields for conceptplan JSONB."""
    must_cover = graph_result.get("must_cover_checklist")
    topic_split = graph_result.get("topic_split")
    domain = graph_result.get("domain")
    if not must_cover and not topic_split and not domain:
        return None
    return {
        "domain": domain or "",
        "topic_split": topic_split or [],
        "must_cover_checklist": must_cover or [],
    }


def _hydration_from_active_version(
    active: StudyMaterialVersion,
) -> tuple[dict[str, Any], str | None]:
    """Build graph initial-state hydration from a persisted version row."""
    hydration: dict[str, Any] = {}
    # Concept plan is regenerated on every improve/regenerate run; only pass the
    # previous plan as revision context so mentor_feedback can reshape it.
    concept_plan = active.concept_plan
    if isinstance(concept_plan, dict):
        if concept_plan.get("must_cover_checklist"):
            hydration["must_cover_checklist"] = concept_plan["must_cover_checklist"]
        if concept_plan.get("topic_split"):
            hydration["topic_split"] = concept_plan["topic_split"]
        if concept_plan.get("domain"):
            hydration["domain"] = concept_plan["domain"]
    elif isinstance(active.qc_result, dict):
        checklist = active.qc_result.get("must_cover_checklist")
        if checklist:
            hydration["must_cover_checklist"] = checklist

    stored_hashes = active.qc_section_content_hashes
    if isinstance(stored_hashes, dict) and stored_hashes:
        hydration["qc_section_content_hashes"] = stored_hashes

    checklist_for_frozen = hydration.get("must_cover_checklist")
    if (
        isinstance(stored_hashes, dict)
        and stored_hashes
        and (active.qc_frozen_check_ids or active.qc_frozen_section_keys)
    ):
        document = parse_generation_document(active.content or "")
        if document is not None:
            pruned_check_ids, pruned_section_ids = effective_frozen_sets(
                frozen_check_ids=active.qc_frozen_check_ids,
                frozen_section_ids=active.qc_frozen_section_keys,
                stored_hashes=stored_hashes,
                document=document,
                checklist=checklist_for_frozen
                if isinstance(checklist_for_frozen, list)
                else None,
            )
            if pruned_check_ids:
                hydration["qc_frozen_check_ids"] = pruned_check_ids
            if pruned_section_ids:
                hydration["qc_frozen_section_keys"] = pruned_section_ids

    failed_qc_feedback: str | None = None
    if isinstance(active.qc_result, dict):
        feedback = format_qc_feedback(active.qc_result)
        if feedback.strip():
            failed_qc_feedback = feedback

    return hydration, failed_qc_feedback


def _resolve_qc_result_for_persist(
    graph_result: dict[str, Any],
) -> tuple[bool, dict[str, Any] | None]:
    """Return ``(qc_failed_permanently, qc_result_dict)`` for DB persistence."""
    qc_attempt = graph_result.get("qc_attempt") or 0

    if graph_result.get("terminal_llm_failure"):
        raw = graph_result.get("qc_result")
        if isinstance(raw, dict):
            return True, _strip_internal_scores_from_qc_dict(
                _enrich_qc_result_dict(raw, graph_result)
            )
        return True, raw

    if not graph_result.get("qc_evaluated"):
        return bool(graph_result.get("qc_failed_permanently")), None

    if qc_attempt == 0:
        return False, None

    qc_failed_permanently = bool(graph_result.get("qc_failed_permanently"))
    raw = graph_result.get("qc_result")

    if isinstance(raw, dict):
        if raw.get("errorType") or raw.get("error_type"):
            return qc_failed_permanently, _strip_internal_scores_from_qc_dict(raw)
        if raw.get("qcInfraError"):
            return qc_failed_permanently, _strip_internal_scores_from_qc_dict(raw)
        return qc_failed_permanently, _enrich_qc_result_dict(raw, graph_result)

    qc_result_out = _build_qc_result_out(graph_result)
    if qc_result_out:
        return qc_failed_permanently, qc_result_out.model_dump(exclude_none=True)
    return qc_failed_permanently, None


class StudyMaterialService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def _start_study_material_run(
        self,
        *,
        node_id: UUID,
        space_id: UUID,
        mentor_id: UUID,
        generation_mode: GenerationRunMode,
        request_params: dict[str, Any],
    ) -> UUID:
        has_reference = bool(request_params.get("reference_material_id"))
        request_params = {
            **request_params,
            "node_id": str(node_id),
            "step_profile": study_step_profile_for_mode(
                generation_mode=generation_mode.value,
                has_reference_material=has_reference,
            ).value,
        }
        resource_type, resource_id = GenerationRunService.resource_for_study_material(
            node_id
        )
        run_service = GenerationRunService(self.session)
        run = await run_service.start_run(
            GenerationRunCreate(
                pipeline=GenerationRunPipeline.STUDY_MATERIAL,
                resource_type=resource_type,
                resource_id=resource_id,
                node_id=node_id,
                space_id=space_id,
                mentor_id=mentor_id,
                generation_mode=generation_mode,
                request_params=request_params,
            )
        )
        return run.run_id

    async def _complete_generation_run(self, run_id: UUID) -> None:
        await GenerationRunService(self.session).complete_run(run_id)

    async def _fail_generation_run(
        self,
        run_id: UUID,
        *,
        graph_result: dict[str, Any] | None = None,
        exc: Exception | None = None,
    ) -> None:
        error_message = (
            str(exc) if exc is not None else "Study material generation failed."
        )
        error_type = type(exc).__name__ if exc is not None else "generation_failed"
        next_retry = None
        if graph_result is not None:
            raw_retry = graph_result.get("next_llm_retry_at")
            if isinstance(raw_retry, datetime):
                next_retry = raw_retry
            error_message = str(graph_result.get("error") or error_message)
            if graph_result.get("terminal_llm_failure"):
                error_type = str(graph_result.get("llm_error_type") or error_type)
        await GenerationRunService(self.session).fail_run(
            run_id,
            error_message=error_message,
            error_type=error_type,
            next_llm_retry_at=next_retry,
        )

    async def _persist_run_result(
        self,
        run_id: UUID,
        result: StudyMaterialGenerateResponse | StudyMaterialFeedbackResponse,
    ) -> None:
        payload: dict[str, Any] = {}
        if isinstance(result, StudyMaterialGenerateResponse):
            payload["study_material_generate"] = result.model_dump(mode="json")
        else:
            payload["study_material_feedback"] = result.model_dump(mode="json")
        await GenerationRunService(self.session).store_run_result(run_id, payload)

    async def resume_study_material_generation(
        self,
        resume_result: GenerationRunResumeResult,
        *,
        user_id: UUID,
        role: str,
    ) -> StudyMaterialGenerateResponse | StudyMaterialFeedbackResponse | None:
        """Continue a failed study material run from its last checkpoint."""
        _assert_mentor(role)
        node_id = resume_result.checkpoint_state.get("node_id")
        if node_id is None:
            node_id = resume_result.request_params.get("node_id")
        if isinstance(node_id, str):
            node_id = UUID(node_id)
        if node_id is None:
            raise LLMGenerationFailedException(
                detail="Resume checkpoint is missing node_id."
            )

        node = await _get_node_and_assert_space_access(
            self.session, node_id, user_id, owner_only=True
        )
        space_id = node.space_id
        node_title = node.title
        run_id = resume_result.run_id
        generation_mode = resume_result.generation_mode

        initial_state = hydrate_checkpoint_state(
            resume_result.checkpoint_state,
            last_completed_node=resume_result.last_completed_node,
            request_params=resume_result.request_params,
        )
        initial_state["generation_mode"] = generation_mode

        try:
            graph_result = await run_study_material_from_checkpoint(
                session=self.session,
                initial_state=initial_state,
                user_id=user_id,
                run_id=run_id,
            )
            graph_result["node_title"] = node_title
            result = await self._finalize_generation_run(
                run_id=run_id,
                node_id=node_id,
                space_id=space_id,
                graph_result=graph_result,
                generation_mode=generation_mode,
                user_id=user_id,
                request_params=resume_result.request_params,
            )
            await self._persist_run_result(run_id, result)
            return result
        except GenerationRunAborted:
            return None
        except Exception as exc:
            await self._fail_generation_run(run_id, exc=exc)
            raise

    async def _finalize_generation_run(
        self,
        *,
        run_id: UUID,
        node_id: UUID,
        space_id: UUID,
        graph_result: dict[str, Any],
        generation_mode: str,
        user_id: UUID,
        request_params: dict[str, Any],
    ) -> StudyMaterialGenerateResponse | StudyMaterialFeedbackResponse:
        if (
            generation_mode == "regenerate"
            and graph_result.get("regenerate_status") == "vague"
        ):
            await self._complete_generation_run(run_id)
            return StudyMaterialFeedbackResponse(
                has_new_version=False,
                status="regeneration_goal_too_vague",
                status_message=graph_result.get("llm_output_content"),
                new_version=None,
                run_id=run_id,
            )

        if (
            generation_mode == "improve"
            and graph_result.get("improve_status") == "vague"
        ):
            await self._complete_generation_run(run_id)
            return StudyMaterialFeedbackResponse(
                has_new_version=False,
                status="feedback_too_vague",
                status_message=graph_result.get("llm_output_content"),
                new_version=None,
                run_id=run_id,
            )

        reference_material_id = graph_result.get("reference_material_id")
        if isinstance(reference_material_id, str):
            reference_material_id = UUID(reference_material_id)
        if reference_material_id is None and request_params.get(
            "reference_material_id"
        ):
            reference_material_id = UUID(str(request_params["reference_material_id"]))

        based_on_version_id = request_params.get("based_on_version_id")
        based_on_uuid = (
            UUID(str(based_on_version_id)) if based_on_version_id is not None else None
        )

        mentor_feedback = request_params.get(
            "mentor_regeneration_goal"
        ) or request_params.get("mentor_feedback")

        version_out = await self._persist_new_version(
            node_id=node_id,
            space_id=space_id,
            graph_result=graph_result,
            generation_type=generation_mode,
            user_id=user_id,
            mentor_feedback_used=mentor_feedback,
            reference_material_id=reference_material_id,
            based_on_version_id=based_on_uuid,
        )
        await self._complete_generation_run(run_id)

        if generation_mode == "generate":
            return StudyMaterialGenerateResponse(
                **version_out.model_dump(),
                run_id=run_id,
            )

        return StudyMaterialFeedbackResponse(
            has_new_version=True,
            new_version_id=version_out.version_id,
            status="ok",
            new_version=version_out,
            qc_failed_permanently=version_out.qc_failed_permanently,
            qc_result=version_out.qc_result,
            run_id=run_id,
        )

    async def _persist_new_version(
        self,
        *,
        node_id: UUID,
        space_id: UUID,
        graph_result: dict[str, Any],
        generation_type: str,
        user_id: UUID,
        mentor_feedback_used: str | None = None,
        reference_material_id: UUID | None = None,
        based_on_version_id: UUID | None = None,
    ) -> StudyMaterialVersionOut:
        repo = StudyMaterialRepository(self.session)
        next_version = await repo.get_next_version_number(node_id)

        active = await repo.get_active_version(node_id)

        qc_failed_permanently, qc_result_dict = _resolve_qc_result_for_persist(
            graph_result
        )
        next_llm_retry_at = graph_result.get("next_llm_retry_at")
        qc_attempt_count = graph_result.get("qc_attempt") or 0
        api_generation_outcome = resolve_api_generation_outcome(graph_result)
        outcome_detail = graph_result.get("generation_outcome_detail")
        if not isinstance(outcome_detail, dict):
            outcome_detail = None

        content = content_for_persistence(graph_result["generated_content"])

        version = await repo.create_version_with_deactivate(
            active_version=active,
            node_id=node_id,
            space_id=space_id,
            version_number=next_version,
            content=content,
            generation_type=generation_type,
            mentor_feedback_used=mentor_feedback_used,
            reference_material_id=reference_material_id,
            based_on_version_id=based_on_version_id,
            llm_model_used=graph_result.get("llm_model_used"),
            prompt_snapshot=embed_effective_instruction_snapshot(
                graph_result.get("prompt_snapshot"),
                graph_result.get("effective_instruction"),
            ),
            token_usage=graph_result.get("token_usage"),
            created_by=user_id,
            qc_failed_permanently=qc_failed_permanently,
            qc_result=qc_result_dict,
            qc_passed=bool(graph_result.get("qc_passed")),
            qc_attempt_count=qc_attempt_count,
            generation_run_id=graph_result.get("artifact_run_id"),
            concept_plan=_build_concept_plan_from_graph(graph_result),
            checklist_llm_model_used=graph_result.get("checklist_llm_model_used"),
            qc_verification_mode=graph_result.get("qc_verification_mode"),
            qc_frozen_check_ids=graph_result.get("qc_frozen_check_ids"),
            qc_frozen_section_keys=graph_result.get("qc_frozen_section_keys"),
            qc_section_content_hashes=graph_result.get("qc_section_content_hashes"),
            next_llm_retry_at=next_llm_retry_at,
            generation_outcome=api_generation_outcome,
            generation_outcome_detail=outcome_detail,
            qc_evaluated=bool(graph_result.get("qc_evaluated")),
        )
        topic_title = graph_result.get("node_title") or str(node_id)
        log_study_material_version(
            topic_title=topic_title,
            version_number=next_version,
            generation_type=generation_type,
            version_id=str(version.version_id),
            node_id=str(node_id),
            content=content,
            graph_result=graph_result,
            mentor_feedback_used=mentor_feedback_used,
        )
        return _study_material_version_out(version)

    # ── generate ───────────────────────────────────────────────────────

    async def start_generate_study_material(
        self,
        node_id: UUID,
        request: StudyMaterialGenerateRequest,
        user_id: UUID,
        role: str,
    ) -> UUID:
        """Validate and create a durable run for first-time generation."""
        _assert_mentor(role)
        node = await _get_node_and_assert_space_access(
            self.session, node_id, user_id, owner_only=True
        )
        return await self._start_study_material_run(
            node_id=node_id,
            space_id=node.space_id,
            mentor_id=user_id,
            generation_mode=GenerationRunMode.GENERATE,
            request_params={
                "reference_material_id": _request_param_uuid(
                    request.reference_material_id
                ),
            },
        )

    async def execute_generate_study_material(
        self,
        *,
        run_id: UUID,
        user_id: UUID,
    ) -> None:
        run_service = GenerationRunService(self.session)
        run = await run_service.acquire_lock_for_run(run_id)
        if run is None:
            return
        params = run.request_params or {}
        node_id = UUID(str(params["node_id"]))
        ref_raw = params.get("reference_material_id")
        reference_material_id = UUID(str(ref_raw)) if ref_raw else None
        node = await _get_node_and_assert_space_access(
            self.session, node_id, user_id, owner_only=True
        )
        try:
            graph_result = await run_study_material_generation(
                session=self.session,
                node_id=node_id,
                reference_material_id=reference_material_id,
                user_id=user_id,
                run_id=run_id,
            )
            graph_result["node_title"] = node.title
            result = await self._finalize_generation_run(
                run_id=run_id,
                node_id=node_id,
                space_id=node.space_id,
                graph_result=graph_result,
                generation_mode="generate",
                user_id=user_id,
                request_params=params,
            )
            await self._persist_run_result(run_id, result)
        except GenerationRunAborted:
            return
        except Exception as exc:
            await self._fail_generation_run(run_id, exc=exc)

    async def _create_durable_run_without_advisory_lock(
        self,
        *,
        node_id: UUID,
        space_id: UUID,
        mentor_id: UUID,
        generation_mode: GenerationRunMode,
        request_params: dict[str, Any],
    ) -> UUID:
        """Persist a RUNNING generation row (caller must hold the advisory lock)."""
        has_reference = bool(request_params.get("reference_material_id"))
        request_params = {
            **request_params,
            "node_id": str(node_id),
            "step_profile": study_step_profile_for_mode(
                generation_mode=generation_mode.value,
                has_reference_material=has_reference,
            ).value,
        }
        resource_type, resource_id = GenerationRunService.resource_for_study_material(
            node_id
        )
        run_service = GenerationRunService(self.session)
        await run_service.repo.supersede_stale_runs(
            resource_id=resource_id,
            pipeline=GenerationRunPipeline.STUDY_MATERIAL.value,
        )
        active = await run_service.repo.get_active_run(
            resource_id=resource_id,
            pipeline=GenerationRunPipeline.STUDY_MATERIAL.value,
        )
        if active is not None and active.status == GenerationRunStatus.RUNNING.value:
            raise GenerationRunConflictException(str(active.run_id))

        run = await run_service.repo.create(
            GenerationRunCreate(
                pipeline=GenerationRunPipeline.STUDY_MATERIAL,
                resource_type=resource_type,
                resource_id=resource_id,
                node_id=node_id,
                space_id=space_id,
                mentor_id=mentor_id,
                generation_mode=generation_mode,
                request_params=request_params,
            )
        )
        await run_service.progress.start(
            run.run_id, GenerationRunPipeline.STUDY_MATERIAL
        )
        return cast(UUID, run.run_id)

    async def generate_study_material_inline(
        self,
        node_id: UUID,
        request: StudyMaterialGenerateRequest,
        user_id: UUID,
        role: str,
    ) -> StudyMaterialGenerateResponse:
        """Create and run generation under one advisory lock (sequential generate-all).

        Unlike the async ``/generate`` path (start → release lock → background
        re-acquire), this holds the per-node lock for the full graph so the next
        node cannot race a stale or leaked lock on Cloud Run.
        """
        _assert_mentor(role)
        node = await _get_node_and_assert_space_access(
            self.session, node_id, user_id, owner_only=True
        )
        resource_type, resource_id = GenerationRunService.resource_for_study_material(
            node_id
        )
        pipeline = GenerationRunPipeline.STUDY_MATERIAL.value

        await require_generation_lock(
            self.session,
            pipeline=pipeline,
            resource_id=resource_id,
        )
        run_id: UUID | None = None
        try:
            run_id = await self._create_durable_run_without_advisory_lock(
                node_id=node_id,
                space_id=node.space_id,
                mentor_id=user_id,
                generation_mode=GenerationRunMode.GENERATE,
                request_params={
                    "reference_material_id": _request_param_uuid(
                        request.reference_material_id
                    ),
                },
            )
            ref_raw = request.reference_material_id
            reference_material_id = UUID(str(ref_raw)) if ref_raw else None
            graph_result = await run_study_material_generation(
                session=self.session,
                node_id=node_id,
                reference_material_id=reference_material_id,
                user_id=user_id,
                run_id=run_id,
            )
            graph_result["node_title"] = node.title
            result = await self._finalize_generation_run(
                run_id=run_id,
                node_id=node_id,
                space_id=node.space_id,
                graph_result=graph_result,
                generation_mode="generate",
                user_id=user_id,
                request_params={
                    "reference_material_id": _request_param_uuid(
                        request.reference_material_id
                    ),
                    "node_id": str(node_id),
                },
            )
            await self._persist_run_result(run_id, result)
            return result
        except GenerationRunAborted:
            raise LLMGenerationFailedException(
                detail="Generation was cancelled."
            ) from None
        except Exception as exc:
            if run_id is not None:
                await self._fail_generation_run(run_id, exc=exc)
            raise
        finally:
            await release_generation_lock(
                self.session,
                pipeline=pipeline,
                resource_id=resource_id,
            )

    # ── regenerate ─────────────────────────────────────────────────────

    async def start_regenerate_study_material(
        self,
        node_id: UUID,
        request: StudyMaterialRegenerateRequest,
        user_id: UUID,
        role: str,
    ) -> UUID:
        """Validate and create a durable run for regeneration."""
        _assert_mentor(role)
        node = await _get_node_and_assert_space_access(
            self.session, node_id, user_id, owner_only=True
        )
        repo = StudyMaterialRepository(self.session)
        active = await repo.get_active_version(node_id)
        if active is None:
            raise StudyMaterialNoActiveVersionException()
        if (
            active.content
            and "GENERATION STATUS: Reference material required" in active.content
        ):
            raise StudyMaterialModificationBlockedReferenceMaterialRequiredException(
                action="regenerate"
            )
        return await self._start_study_material_run(
            node_id=node_id,
            space_id=node.space_id,
            mentor_id=user_id,
            generation_mode=GenerationRunMode.REGENERATE,
            request_params={
                "mentor_regeneration_goal": request.mentor_regeneration_goal,
                "reference_material_id": _request_param_uuid(
                    active.reference_material_id
                ),
                "based_on_version_id": _request_param_uuid(active.version_id),
            },
        )

    async def execute_regenerate_study_material(
        self,
        *,
        run_id: UUID,
        user_id: UUID,
    ) -> None:
        run_service = GenerationRunService(self.session)
        run = await run_service.acquire_lock_for_run(run_id)
        if run is None:
            return
        params = run.request_params or {}
        node_id = UUID(str(params["node_id"]))
        node = await _get_node_and_assert_space_access(
            self.session, node_id, user_id, owner_only=True
        )
        repo = StudyMaterialRepository(self.session)
        active = await repo.get_active_version(node_id)
        if active is None:
            await self._fail_generation_run(
                run_id, exc=StudyMaterialNoActiveVersionException()
            )
            return
        reference_material_id = active.reference_material_id
        hydration, failed_qc_feedback = _hydration_from_active_version(active)
        mentor_goal = str(params.get("mentor_regeneration_goal") or "")
        try:
            graph_result = await run_study_material_regeneration(
                session=self.session,
                node_id=node_id,
                current_draft_content=active.content,
                mentor_regeneration_goal=mentor_goal,
                reference_material_id=reference_material_id,
                user_id=user_id,
                hydration=hydration,
                failed_qc_feedback=failed_qc_feedback,
                run_id=run_id,
            )
            graph_result["node_title"] = node.title
            result = await self._finalize_generation_run(
                run_id=run_id,
                node_id=node_id,
                space_id=node.space_id,
                graph_result=graph_result,
                generation_mode="regenerate",
                user_id=user_id,
                request_params=params,
            )
            await self._persist_run_result(run_id, result)
        except GenerationRunAborted:
            return
        except Exception as exc:
            await self._fail_generation_run(run_id, exc=exc)

    # ── improve ────────────────────────────────────────────────────────

    async def start_improve_study_material(
        self,
        node_id: UUID,
        request: StudyMaterialImproveRequest,
        user_id: UUID,
        role: str,
    ) -> UUID:
        """Validate and create a durable run for improvement."""
        _assert_mentor(role)
        node = await _get_node_and_assert_space_access(
            self.session, node_id, user_id, owner_only=True
        )
        repo = StudyMaterialRepository(self.session)
        active = await repo.get_active_version(node_id)
        if active is None:
            raise StudyMaterialNoActiveVersionException()
        if (
            active.content
            and "GENERATION STATUS: Reference material required" in active.content
        ):
            raise StudyMaterialModificationBlockedReferenceMaterialRequiredException(
                action="improve"
            )
        return await self._start_study_material_run(
            node_id=node_id,
            space_id=node.space_id,
            mentor_id=user_id,
            generation_mode=GenerationRunMode.IMPROVE,
            request_params={
                "mentor_feedback": request.mentor_feedback,
                "reference_material_id": _request_param_uuid(
                    active.reference_material_id
                ),
                "based_on_version_id": _request_param_uuid(active.version_id),
            },
        )

    async def execute_improve_study_material(
        self,
        *,
        run_id: UUID,
        user_id: UUID,
    ) -> None:
        run_service = GenerationRunService(self.session)
        run = await run_service.acquire_lock_for_run(run_id)
        if run is None:
            return
        params = run.request_params or {}
        node_id = UUID(str(params["node_id"]))
        node = await _get_node_and_assert_space_access(
            self.session, node_id, user_id, owner_only=True
        )
        repo = StudyMaterialRepository(self.session)
        active = await repo.get_active_version(node_id)
        if active is None:
            await self._fail_generation_run(
                run_id, exc=StudyMaterialNoActiveVersionException()
            )
            return
        reference_material_id = active.reference_material_id
        hydration, failed_qc_feedback = _hydration_from_active_version(active)
        mentor_feedback = str(params.get("mentor_feedback") or "")
        try:
            graph_result = await run_study_material_improve(
                session=self.session,
                node_id=node_id,
                current_draft_content=active.content,
                mentor_feedback=mentor_feedback,
                reference_material_id=reference_material_id,
                user_id=user_id,
                hydration=hydration,
                failed_qc_feedback=failed_qc_feedback,
                run_id=run_id,
            )
            graph_result["node_title"] = node.title
            result = await self._finalize_generation_run(
                run_id=run_id,
                node_id=node_id,
                space_id=node.space_id,
                graph_result=graph_result,
                generation_mode="improve",
                user_id=user_id,
                request_params=params,
            )
            await self._persist_run_result(run_id, result)
        except GenerationRunAborted:
            return
        except Exception as exc:
            await self._fail_generation_run(run_id, exc=exc)

    # ── manual edit ────────────────────────────────────────────────────

    async def manual_edit_study_material(
        self,
        node_id: UUID,
        request: StudyMaterialManualEditRequest,
        user_id: UUID,
        role: str,
    ) -> StudyMaterialVersionOut:
        """Creates vN+1 directly from mentor rich-text input. No LLM call."""
        _assert_mentor(role)
        node = await _get_node_and_assert_space_access(
            self.session, node_id, user_id, owner_only=True
        )
        space_id = node.space_id
        node_title = node.title

        repo = StudyMaterialRepository(self.session)
        active = await repo.get_active_version(node_id)
        if (
            active is not None
            and active.content
            and "GENERATION STATUS: Reference material required" in active.content
        ):
            raise StudyMaterialModificationBlockedReferenceMaterialRequiredException(
                action="manually edit"
            )
        based_on = active.version_id if active is not None else None
        reference_material_id = active.reference_material_id if active else None

        if active is not None:
            await repo.deactivate_version(active)

        next_version = await repo.get_next_version_number(node_id)
        version = await repo.create_version(
            node_id=node_id,
            space_id=space_id,
            version_number=next_version,
            content=request.content,
            generation_type="manual_edit",
            mentor_feedback_used=None,
            reference_material_id=reference_material_id,
            based_on_version_id=based_on,
            llm_model_used=None,
            prompt_snapshot=None,
            token_usage=None,
            is_active=True,
            created_by=user_id,
        )
        log_study_material_version(
            topic_title=node_title,
            version_number=next_version,
            generation_type="manual_edit",
            version_id=str(version.version_id),
            node_id=str(node_id),
            content=request.content,
            graph_result={},
            mentor_feedback_used=None,
        )
        return _study_material_version_out(version)

    # ── publish preview / confirm ──────────────────────────────────────

    async def _load_publish_target(
        self,
        node_id: UUID,
        version_id: UUID,
        user_id: UUID,
        role: str,
    ) -> tuple:
        _assert_mentor(role)
        node = await _get_node_and_assert_space_access(
            self.session, node_id, user_id, owner_only=True
        )
        space = await _get_space_and_assert_owner(self.session, node.space_id, user_id)
        if not space.is_published:
            raise StudyMaterialPublishBlockedSpaceUnpublishedException()

        repo = StudyMaterialRepository(self.session)
        version = await repo.get_version_by_id(version_id)
        if version is None or version.node_id != node_id:
            raise StudyMaterialVersionMismatchException()
        if version.is_published:
            raise StudyMaterialVersionAlreadyPublishedException()
        if (
            version.content
            and "GENERATION STATUS: Reference material required" in version.content
        ):
            raise StudyMaterialPublishBlockedReferenceMaterialRequiredException()
        return node, version, repo

    async def preview_publish_study_material(
        self,
        node_id: UUID,
        version_id: UUID,
        user_id: UUID,
        role: str,
    ) -> StudyMaterialPublishPreviewOut:
        """Return pre-publish confirmation requirements without writing."""
        _, version, repo = await self._load_publish_target(
            node_id, version_id, user_id, role
        )
        previous = await repo.get_published_version(node_id)
        new_label = build_version_display_label(
            version.version_number, version.generation_type
        )

        will_reset_trainee_read_progress = False
        previous_label: str | None = None
        current_published_label: str | None = None
        is_republishing_older = False

        if previous is not None:
            previous_label = build_version_display_label(
                previous.version_number, previous.generation_type
            )
            current_published_label = previous_label
            is_republishing_older = version.version_number < previous.version_number
            will_reset_trainee_read_progress = previous.version_id != version.version_id

        requires_confirmation = previous is not None
        is_replacing_live_version = previous is not None
        return StudyMaterialPublishPreviewOut(
            requires_confirmation=requires_confirmation,
            previous_version_label=previous_label,
            new_version_label=new_label,
            is_republishing_older=is_republishing_older,
            current_published_version_label=current_published_label,
            will_reset_trainee_read_progress=will_reset_trainee_read_progress,
            is_replacing_live_version=is_replacing_live_version,
        )

    async def publish_study_material(
        self,
        node_id: UUID,
        request: StudyMaterialPublishRequest,
        user_id: UUID,
        role: str,
    ) -> StudyMaterialVersionOut:
        """Publish a version; quiz lifecycle on the node is unchanged (Option B)."""
        _, version, repo = await self._load_publish_target(
            node_id, request.version_id, user_id, role
        )
        previous = await repo.get_published_version(node_id)

        superseded_retention_mode = (
            request.superseded_retention_mode or RetentionMode.keep_for_review
        )

        await execute_publish_version_cascade(
            self.session,
            node_id=node_id,
            target_version=version,
            previous_published_version=previous,
            published_by=user_id,
            superseded_retention_mode=superseded_retention_mode,
        )
        fresh = await repo.get_version_by_id(request.version_id)
        if fresh is None:
            raise StudyMaterialNotFoundException()
        return _study_material_version_out(fresh)

    async def preview_unpublish_study_material(
        self,
        node_id: UUID,
        version_id: UUID,
        user_id: UUID,
        role: str,
    ) -> StudyMaterialUnpublishPreviewOut:
        """Return pre-unpublish info with engagement counts without writing."""
        _assert_mentor(role)
        node = await _get_node_and_assert_space_access(
            self.session, node_id, user_id, owner_only=True
        )

        repo = StudyMaterialRepository(self.session)
        version = await repo.get_version_by_id(version_id)
        if version is None or version.node_id != node_id:
            raise StudyMaterialVersionMismatchException()
        if not version.is_published:
            raise StudyMaterialVersionNotPublishedException()

        version_label = build_version_display_label(
            version.version_number, version.generation_type
        )

        progress_repo = MentorProgressRepository(self.session)
        trainees_read_count = await progress_repo.count_trainees_with_read_progress(
            node_id, node.space_id
        )
        trainees_quiz_attempt_count = (
            await progress_repo.count_trainees_with_quiz_attempts(node_id)
        )

        quiz_repo = TraineeQuizRepository(self.session)
        live_quiz = await quiz_repo.get_published_quiz_by_node(node_id)
        has_live_quiz = live_quiz is not None
        live_quiz_title = live_quiz.title if live_quiz is not None else None

        return StudyMaterialUnpublishPreviewOut(
            requires_confirmation=True,
            version_label=version_label,
            trainees_read_count=trainees_read_count,
            trainees_quiz_attempt_count=trainees_quiz_attempt_count,
            has_live_quiz=has_live_quiz,
            live_quiz_title=live_quiz_title,
        )

    async def unpublish_study_material(
        self,
        node_id: UUID,
        request: StudyMaterialUnpublishRequest,
        user_id: UUID,
        role: str,
    ) -> StudyMaterialVersionOut:
        """Unpublish version with a retention choice; quiz lifecycle is unchanged."""
        _assert_mentor(role)
        await _get_node_and_assert_space_access(
            self.session, node_id, user_id, owner_only=True
        )

        repo = StudyMaterialRepository(self.session)
        version = await repo.get_version_by_id(request.version_id)
        if version is None or version.node_id != node_id:
            raise StudyMaterialVersionMismatchException()
        if not version.is_published:
            raise StudyMaterialVersionNotPublishedException()

        await execute_unpublish_version_cascade(
            self.session,
            node_id=node_id,
            version=version,
            retention_mode=request.retention_mode,
        )
        fresh = await repo.get_version_by_id(request.version_id)
        if fresh is None:
            raise StudyMaterialNotFoundException()
        return _study_material_version_out(fresh)

    # ── activate ───────────────────────────────────────────────────────

    async def activate_study_material(
        self,
        node_id: UUID,
        request: StudyMaterialActivateRequest,
        user_id: UUID,
        role: str,
    ) -> StudyMaterialVersionOut:
        """Atomically deactivates the current active version and activates the target."""
        _assert_mentor(role)
        await _get_node_and_assert_space_access(
            self.session, node_id, user_id, owner_only=True
        )

        repo = StudyMaterialRepository(self.session)
        target = await repo.get_version_by_id(request.version_id)
        if target is None or target.node_id != node_id:
            raise StudyMaterialVersionMismatchException()

        if target.is_archived:
            target = await repo.unarchive_version(target)

        current_active = await repo.get_active_version(node_id)
        if (
            current_active is not None
            and current_active.version_id != target.version_id
        ):
            await repo.deactivate_version(current_active)
            target = await repo.get_version_by_id(request.version_id)
            if target is None or target.node_id != node_id:
                raise StudyMaterialVersionMismatchException()

        target = await repo.activate_version(target)
        return _study_material_version_out(target)

    # ── archive / unarchive ──────────────────────────────────────────

    async def archive_study_material_version(
        self,
        node_id: UUID,
        version_id: UUID,
        user_id: UUID,
        role: str,
    ) -> StudyMaterialVersionOut:
        """Move a WIP draft to the mentor archive shelf (``is_archived``).

        Orthogonal to trainee ``lifecycle_status``: shelf-archived rows are never
        trainee-visible regardless of lifecycle. Only ``lifecycle_status='draft'``
        WIP versions may be shelved — superseded trainee history and published
        layers use lifecycle transitions instead.
        """
        _assert_mentor(role)
        await _get_node_and_assert_space_access(
            self.session, node_id, user_id, owner_only=True
        )

        repo = StudyMaterialRepository(self.session)
        version = await repo.get_version_by_id(version_id)
        if version is None or version.node_id != node_id:
            raise StudyMaterialVersionMismatchException()
        if version.is_archived:
            raise StudyMaterialVersionAlreadyArchivedException()
        if version.is_published:
            raise StudyMaterialCannotArchivePublishedException()
        if version.lifecycle_status != LIFECYCLE_DRAFT:
            raise StudyMaterialCannotArchiveNonDraftException()

        version = await repo.archive_version(version, archived_by=user_id)
        archived = await repo.get_version_by_id(version_id)
        if archived is None:
            raise StudyMaterialVersionMismatchException()
        return _study_material_version_out(archived)

    async def unarchive_study_material_version(
        self,
        node_id: UUID,
        version_id: UUID,
        user_id: UUID,
        role: str,
    ) -> StudyMaterialVersionOut:
        """Restore a shelf-archived WIP draft to the mentor working history.

        Does not publish or change ``lifecycle_status`` — the version returns to
        the draft workflow only. Trainee lifecycle archive rows cannot be
        restored to the working shelf.
        """
        _assert_mentor(role)
        await _get_node_and_assert_space_access(
            self.session, node_id, user_id, owner_only=True
        )

        repo = StudyMaterialRepository(self.session)
        version = await repo.get_version_by_id(version_id)
        if version is None or version.node_id != node_id:
            raise StudyMaterialVersionMismatchException()
        if not version.is_archived:
            raise StudyMaterialVersionNotArchivedException()
        if version.lifecycle_status == LIFECYCLE_ARCHIVED:
            raise StudyMaterialCannotUnarchiveTraineeHistoryException()

        version = await repo.unarchive_version(version)

        current_active = await repo.get_active_version(node_id)
        if (
            current_active is not None
            and current_active.version_id != version.version_id
        ):
            await repo.deactivate_version(current_active)
            version = await repo.get_version_by_id(version_id)
            if version is None or version.node_id != node_id:
                raise StudyMaterialVersionMismatchException()

        if not version.is_active:
            version = await repo.activate_version(version)

        restored = await repo.get_version_by_id(version_id)
        if restored is None:
            raise StudyMaterialVersionMismatchException()
        return _study_material_version_out(restored)

    async def dismiss_study_material_qc_warning(
        self,
        node_id: UUID,
        version_id: UUID,
        user_id: UUID,
        role: str,
    ) -> StudyMaterialVersionOut:
        """Record that the mentor accepted a draft despite a permanent QC failure."""
        _assert_mentor(role)
        await _get_node_and_assert_space_access(
            self.session, node_id, user_id, owner_only=True
        )

        repo = StudyMaterialRepository(self.session)
        version = await repo.get_version_by_id(version_id)
        if version is None or version.node_id != node_id:
            raise StudyMaterialVersionMismatchException()

        dismissed = await repo.dismiss_qc_warning(version_id)
        if dismissed is None:
            raise StudyMaterialVersionMismatchException()
        await self.session.commit()
        return _study_material_version_out(dismissed)

    # ── list versions ──────────────────────────────────────────────────

    async def list_versions(
        self,
        node_id: UUID,
        user_id: UUID,
        role: str,
        *,
        archived: bool = False,
        viewing_version_id: UUID | None = None,
    ) -> StudyMaterialVersionHistoryOut:
        """Returns versions ordered by version_number DESC.

        archived=False — working history (default).
        archived=True — archive shelf.
        """
        node = await _get_node_and_assert_space_access(
            self.session, node_id, user_id, owner_only=False
        )
        await _assert_space_access(self.session, node.space_id, user_id, role)

        repo = StudyMaterialRepository(self.session)
        if role == "mentor":
            await repo.reconcile_published_versions(node_id)
        versions = await repo.get_all_versions(node_id, archived=archived)
        all_versions = await repo.get_all_versions(node_id, archived=None)
        version_lookup = {v.version_id: v for v in all_versions}
        summaries = [
            StudyMaterialVersionSummary.from_version_row(
                v,
                version_lookup=version_lookup,
                viewing_version_id=viewing_version_id,
            )
            for v in versions
        ]
        return StudyMaterialVersionHistoryOut(
            node_id=node_id,
            versions=summaries,
            total=len(summaries),
        )

    # ── get single version ─────────────────────────────────────────────

    async def get_version(
        self, node_id: UUID, version_id: UUID, user_id: UUID, role: str
    ) -> StudyMaterialVersionOut:
        """Fetch a single version by ID. Validates it belongs to the node."""
        node = await _get_node_and_assert_space_access(
            self.session, node_id, user_id, owner_only=False
        )
        await _assert_space_access(self.session, node.space_id, user_id, role)

        repo = StudyMaterialRepository(self.session)
        version = await repo.get_version_by_id(version_id)
        if version is None or version.node_id != node_id:
            raise StudyMaterialNotFoundException()

        return _study_material_version_out(version)

    async def download_version_pdf(
        self, node_id: UUID, version_id: UUID, user_id: UUID, role: str
    ) -> tuple[bytes, str]:
        """Render a mentor-accessible study material version as PDF."""
        _assert_mentor(role)
        node = await _get_node_and_assert_space_access(
            self.session, node_id, user_id, owner_only=False
        )
        await _assert_space_access(self.session, node.space_id, user_id, role)

        repo = StudyMaterialRepository(self.session)
        version = await repo.get_version_by_id(version_id)
        if version is None or version.node_id != node_id:
            raise StudyMaterialNotFoundException()
        if not is_mentor_accessible_sm(version):
            raise StudyMaterialNotFoundException()
        if not (version.content or "").strip():
            raise StudyMaterialNotFoundException()
        if "GENERATION STATUS: Reference material required" in (version.content or ""):
            raise StudyMaterialModificationBlockedReferenceMaterialRequiredException()

        try:
            pdf_bytes = render_study_material_pdf(node.title, version.content)
        except ValueError:
            raise StudyMaterialPdfGenerationFailedException() from None

        filename = build_study_material_pdf_filename(
            f"{node.title}-v{version.version_number}"
        )
        return pdf_bytes, filename

    # ── active version ─────────────────────────────────────────────────

    async def get_active_version(
        self, node_id: UUID, user_id: UUID, role: str
    ) -> StudyMaterialVersionOut | None:
        """Return the current active study material version for a node, if any."""
        node = await _get_node_and_assert_space_access(
            self.session, node_id, user_id, owner_only=False
        )
        await _assert_space_access(self.session, node.space_id, user_id, role)

        repo = StudyMaterialRepository(self.session)
        active = await repo.get_active_version(node_id)
        if active is None:
            return None
        return _study_material_version_out(active)

    async def get_mentor_ui_state(
        self,
        node_id: UUID,
        user_id: UUID,
        role: str,
        *,
        viewing_version_id: UUID | None = None,
    ) -> StudyMaterialMentorUiStateOut:
        """Resolve mentor study-material UI flags and allowed actions."""
        _assert_mentor(role)
        node = await _get_node_and_assert_space_access(
            self.session, node_id, user_id, owner_only=True
        )
        space = await _get_space_and_assert_owner(self.session, node.space_id, user_id)
        space_is_published = bool(space.is_published)

        node_repo = NodeRepository(self.session)
        ancestors = await node_repo.get_ancestors(node)
        parts = resolve_effective_instruction_parts(node, ancestors)
        # Use the SAME canonical formatter used at generation time so the
        # stored snapshot and this freshly-resolved string are directly
        # comparable. Comparing differently-formatted strings made
        # instruction_changed_since_generation true on every reload/navigation.
        current_instruction = format_effective_instruction(parts)

        sm_repo = StudyMaterialRepository(self.session)
        all_versions = await sm_repo.get_all_versions(node_id, archived=None)
        active = await sm_repo.get_active_version(node_id)
        has_versions = any(is_mentor_visible_sm(v) for v in all_versions)
        has_workspace_versions = any(is_mentor_openable_sm(v) for v in all_versions)

        generation_snapshot: str | None = None
        instruction_changed = False
        if active is not None:
            generation_snapshot = extract_effective_instruction_snapshot(
                active.prompt_snapshot
            )
            if generation_snapshot is not None:
                instruction_changed = generation_snapshot != current_instruction

        displayed_version = None
        target_version_id = viewing_version_id or (
            active.version_id if active is not None else None
        )
        published = await sm_repo.get_published_version(node_id)
        if target_version_id is not None:
            target = await sm_repo.get_version_by_id(target_version_id)
            if target is not None and target.node_id == node_id:
                displayed_version = compute_version_allowed_actions(
                    version_id=target.version_id,
                    version_number=target.version_number,
                    is_active=target.is_active,
                    is_published=target.is_published,
                    is_archived=target.is_archived,
                    active_version_id=active.version_id if active else None,
                    viewing_version_id=viewing_version_id,
                    published_version_id=published.version_id if published else None,
                    published_version_number=(
                        published.version_number if published else None
                    ),
                    space_is_published=space_is_published,
                    content=target.content,
                )

        can_access_quiz = bool(
            space_is_published
            and has_workspace_versions
            and any(
                is_mentor_accessible_sm(version) and (version.content or "").strip()
                for version in all_versions
            )
        )

        student_visibility = await build_mentor_student_visibility(
            self.session, node_id
        )

        return StudyMaterialMentorUiStateOut(
            node_id=node_id,
            has_versions=has_versions,
            has_workspace_versions=has_workspace_versions,
            active_version_id=active.version_id if active else None,
            published_version_id=published.version_id if published else None,
            can_access_study_material=has_versions,
            can_access_quiz=can_access_quiz,
            instruction_changed_since_generation=instruction_changed,
            current_effective_instruction=current_instruction,
            generation_instruction_snapshot=generation_snapshot,
            displayed_version_actions=displayed_version,
            student_visibility=student_visibility,
        )

    # ── clear all drafts ───────────────────────────────────────────────

    async def get_clear_drafts_eligibility(
        self, node_id: UUID, user_id: UUID, role: str
    ) -> StudyMaterialClearDraftsEligibilityOut:
        """Check whether draft study material can be discarded for a node."""
        _assert_mentor(role)
        await _get_node_and_assert_space_access(
            self.session, node_id, user_id, owner_only=True
        )

        sm_repo = StudyMaterialRepository(self.session)
        versions = await sm_repo.get_all_versions(node_id, archived=None)
        discardable_versions = [v for v in versions if is_mentor_discardable_sm(v)]
        version_count = len(discardable_versions)
        blocking_quiz_count = await count_blocking_quizzes_for_clear_drafts(
            self.session,
            node_id,
        )

        if version_count == 0:
            return StudyMaterialClearDraftsEligibilityOut(
                can_clear=False,
                version_count=0,
                quiz_count=blocking_quiz_count,
                block_reason=_clear_drafts_block_reason_no_discardable_versions(
                    versions=versions,
                    blocking_quiz_count=blocking_quiz_count,
                ),
            )

        if blocking_quiz_count > 0:
            noun = "quiz" if blocking_quiz_count == 1 else "quizzes"
            return StudyMaterialClearDraftsEligibilityOut(
                can_clear=False,
                version_count=version_count,
                quiz_count=blocking_quiz_count,
                block_reason=(
                    f"This topic has {blocking_quiz_count} live or active draft {noun}. "
                    "Delete or unpublish them before discarding study material drafts."
                ),
            )

        live_sm_count = sum(1 for v in versions if is_trainee_live_sm(v))
        if live_sm_count > 0:
            noun = "version is" if live_sm_count == 1 else "versions are"
            return StudyMaterialClearDraftsEligibilityOut(
                can_clear=False,
                version_count=version_count,
                quiz_count=0,
                block_reason=(
                    f"{live_sm_count} live study material {noun} visible to trainees. "
                    "Unpublish before discarding drafts."
                ),
            )

        return StudyMaterialClearDraftsEligibilityOut(
            can_clear=True,
            version_count=version_count,
            quiz_count=0,
            block_reason=None,
        )

    async def clear_all_drafts(
        self, node_id: UUID, user_id: UUID, role: str
    ) -> StudyMaterialClearDraftsOut:
        """Discard draft study material versions (and linked draft quizzes) for a node."""
        eligibility = await self.get_clear_drafts_eligibility(node_id, user_id, role)
        if not eligibility.can_clear:
            if eligibility.quiz_count > 0:
                raise StudyMaterialClearDraftsBlockedByQuizException(
                    eligibility.quiz_count
                )
            raise StudyMaterialNoDraftsException()

        sm_repo = StudyMaterialRepository(self.session)
        discarded_count = await sm_repo.discard_draft_versions_for_node(node_id)
        return StudyMaterialClearDraftsOut(
            node_id=node_id,
            discarded_count=discarded_count,
        )

    async def get_space_published_resources(
        self, space_id: UUID, user_id: UUID, role: str
    ) -> SpacePublishedResourcesResponse:
        """Resolve all published topics, study materials, and quizzes in a space."""
        _assert_mentor(role)
        await _assert_space_access(self.session, space_id, user_id, role)

        from sqlalchemy import and_, select

        from src.api.data.models.postgres.e_learning_content.quizzes import Quiz
        from src.api.data.models.postgres.e_learning_content.study_material_versions import (
            StudyMaterialVersion,
        )
        from src.api.data.models.postgres.e_spaces_trees.topic_nodes import TopicNode

        # Fetch active nodes
        nodes_stmt = select(TopicNode).where(
            and_(
                TopicNode.space_id == space_id,
                TopicNode.is_active.is_(True),
            )
        )
        nodes_res = await self.session.execute(nodes_stmt)
        nodes = list(nodes_res.scalars().all())

        # Fetch published study materials
        sm_stmt = select(StudyMaterialVersion).where(
            and_(
                StudyMaterialVersion.space_id == space_id,
                StudyMaterialVersion.is_published.is_(True),
            )
        )
        sm_res = await self.session.execute(sm_stmt)
        sms = list(sm_res.scalars().all())

        # Fetch published quizzes
        quiz_stmt = select(Quiz).where(
            and_(
                Quiz.space_id == space_id,
                Quiz.is_published.is_(True),
            )
        )
        quiz_res = await self.session.execute(quiz_stmt)
        quizzes = list(quiz_res.scalars().all())

        # Combine
        sm_map = {sm.node_id: sm.version_id for sm in sms}
        quiz_map = {q.node_id: q.quiz_id for q in quizzes}

        published_topics = []
        for node in nodes:
            version_id = sm_map.get(node.node_id)
            quiz_id = quiz_map.get(node.node_id)
            if version_id or quiz_id:
                published_topics.append(
                    PublishedResourceTopicSummary(
                        node_id=node.node_id,
                        topic_title=node.title,
                        published_study_material_version_id=version_id,
                        published_quiz_id=quiz_id,
                    )
                )

        return SpacePublishedResourcesResponse(
            space_id=space_id,
            published_topics=published_topics,
        )

    async def get_space_republish_checklist(
        self, space_id: UUID, user_id: UUID, role: str
    ) -> SpaceRepublishChecklistOut:
        """List per-node content mentors can re-publish after espace republish."""
        _assert_mentor(role)
        await _assert_space_access(self.session, space_id, user_id, role)

        from sqlalchemy import and_, select

        from src.api.data.models.postgres.e_learning_content.quizzes import Quiz
        from src.api.data.models.postgres.e_spaces_trees.topic_nodes import TopicNode

        nodes_stmt = select(TopicNode).where(
            and_(
                TopicNode.space_id == space_id,
                TopicNode.is_active.is_(True),
            )
        )
        nodes_res = await self.session.execute(nodes_stmt)
        nodes = list(nodes_res.scalars().all())

        sm_repo = StudyMaterialRepository(self.session)
        checklist: list[RepublishChecklistNodeOut] = []

        for node in nodes:
            versions = await sm_repo.get_all_versions(node.node_id, archived=False)
            publishable_versions = [v for v in versions if (v.content or "").strip()]
            latest_sm = (
                max(publishable_versions, key=lambda v: v.version_number)
                if publishable_versions
                else None
            )

            quiz_stmt = (
                select(Quiz)
                .where(
                    and_(
                        Quiz.node_id == node.node_id,
                        Quiz.space_id == space_id,
                        Quiz.is_published.is_(False),
                    )
                )
                .order_by(Quiz.created_at.desc())
            )
            quiz_res = await self.session.execute(quiz_stmt)
            draft_quiz = quiz_res.scalars().first()

            if latest_sm is None and draft_quiz is None:
                continue

            checklist.append(
                RepublishChecklistNodeOut(
                    node_id=node.node_id,
                    node_title=node.title,
                    last_published_version_id=(
                        latest_sm.version_id if latest_sm is not None else None
                    ),
                    last_published_version_label=(
                        build_version_display_label(
                            latest_sm.version_number, latest_sm.generation_type
                        )
                        if latest_sm is not None
                        else None
                    ),
                    has_unpublished_quiz=draft_quiz is not None,
                    quiz_id=draft_quiz.quiz_id if draft_quiz is not None else None,
                    quiz_title=draft_quiz.title if draft_quiz is not None else None,
                )
            )

        return SpaceRepublishChecklistOut(
            space_id=space_id,
            nodes_with_publishable_material=checklist,
        )
