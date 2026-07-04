# src/api/control/study_agent/nodes/quality_check_node.py
"""Quality-check node — JSON structure extraction + Groq Llama 70B QC verification."""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.runnables import RunnableConfig

from src.api.config import llm_settings
from src.api.control.study_agent.prompts.qc import qc_retry_verification_prompt
from src.api.control.study_agent.states.state import StudyMaterialGraphState
from src.api.utils.study_agent_utils.graph import node_helpers as helpers
from src.api.utils.study_agent_utils.quality_check_utils.checks.block_placement_checks import (
    block_placement_checks,
)
from src.api.utils.study_agent_utils.quality_check_utils.checks.deterministic import (
    build_code_review_payloads,
    extract_structure_from_document,
    structure_check,
    structure_coverage_missing_ids,
)
from src.api.utils.study_agent_utils.quality_check_utils.core.constants import (
    DEFAULT_INSTRUCTION,
    MAX_QC_ATTEMPTS,
)
from src.api.utils.study_agent_utils.quality_check_utils.core.frozen_sets import (
    accumulate_frozen_sets,
)
from src.api.utils.study_agent_utils.quality_check_utils.document.document_merge import (
    build_document_outline,
)
from src.api.utils.study_agent_utils.quality_check_utils.document.targeted_merge import (
    merge_targeted_qc_checks,
)
from src.api.utils.study_agent_utils.quality_check_utils.infra.artifact_logging import (
    log_qc_agent,
    pipeline_attempt,
)
from src.api.utils.study_agent_utils.quality_check_utils.infra.infra_failure import (
    build_infra_failure_return,
    resolve_qc_infra_error_type,
)
from src.api.utils.study_agent_utils.quality_check_utils.results.feedback import (
    format_qc_feedback,
)
from src.api.utils.study_agent_utils.quality_check_utils.results.node_returns import (
    build_qc_guard_return,
)
from src.api.utils.study_agent_utils.quality_check_utils.results.result_builder import (
    build_final_qc_result,
    qc_models_used,
)
from src.api.utils.study_agent_utils.quality_check_utils.results.retry_routing import (
    classify_retry_routing,
)
from src.api.utils.study_agent_utils.quality_check_utils.results.scoring import (
    is_qc_deliverable,
)
from src.api.utils.study_agent_utils.quality_check_utils.verification.verification_pass import (
    run_retry_verification_pass,
    run_verification_pass,
)

logger = logging.getLogger(__name__)


async def quality_check_node(
    state: StudyMaterialGraphState,
    config: RunnableConfig,
) -> dict[str, Any]:
    """Run JSON structure extraction + Groq Llama 70B QC verification."""
    current_attempt = state.get("qc_attempt") or 0

    outcome = state.get("generation_outcome")
    if outcome != "study_document":
        logger.error("QC invoked for non-study outcome: %s", outcome)
        return build_qc_guard_return(
            state,
            reason=f"non-study outcome: {outcome}",
        )

    if state.get("terminal_llm_failure"):
        logger.info("QC guard: terminal LLM failure")
        return build_qc_guard_return(state, reason="terminal_llm_failure")

    if state.get("error") or not state.get("generated_content"):
        logger.info("QC guard: error or no generated content")
        return build_qc_guard_return(state, reason="error or missing content")

    document = state.get("generation_parsed_document")
    if not document:
        logger.error("QC invoked without generation_parsed_document")
        return build_qc_guard_return(state, reason="missing parsed document")

    teaching_instruction = state.get("effective_instruction") or DEFAULT_INSTRUCTION
    generated_content = state.get("generated_content") or ""
    must_cover_checklist: list[dict[str, Any]] = state.get("must_cover_checklist") or []
    topic_split: list[dict[str, Any]] = state.get("topic_split") or []
    new_attempt = current_attempt + 1
    attempt = pipeline_attempt(state)
    topic_title = state.get("node_title") or ""
    domain = state.get("domain") or ""

    if not helpers.groq_api_keys_configured():
        logger.error("QC skipped: no Groq API keys are configured")
        result = build_infra_failure_return(
            new_attempt=new_attempt,
            error_type="llm_infra_error",
            extraction_snapshot=None,
            suggestion="Configure GROQ_API_KEY (and optional rotation keys).",
        )
        log_qc_agent(
            state,
            agent="qc_result",
            pipeline_attempt=attempt,
            payload={
                "qc_passed": False,
                "fail_open": False,
                "qc_inconclusive": True,
                "verification_mode": None,
                "qc_result": result["qc_result"],
            },
        )
        return result

    structure = extract_structure_from_document(document)
    code_review_payloads = build_code_review_payloads(structure)
    structure_missing_ids = structure_coverage_missing_ids(
        document,
        must_cover_checklist,
        topic_split=topic_split,
    )
    optional_structure_check = structure_check(
        structure,
        checklist=must_cover_checklist,
        doc=document,
        topic_split=topic_split,
        structure_missing_ids=structure_missing_ids,
    )
    structure_checks: list[dict[str, Any]] = []
    if optional_structure_check:
        structure_checks.append(optional_structure_check)
    block_placement_failures = block_placement_checks(
        document,
        domain=domain,
        checklist=must_cover_checklist,
    )
    structure_checks.extend(block_placement_failures)

    extraction_snapshot = {
        "sections": [s.get("heading", "") for s in structure.sections],
        "code_review_payloads": code_review_payloads,
        "structure_check": optional_structure_check,
        "block_placement_checks": block_placement_failures,
        "block_placement_check_ids": [c.get("id") for c in block_placement_failures],
    }

    log_qc_agent(
        state,
        agent="qc_extraction",
        pipeline_attempt=attempt,
        payload={
            "section_headings": extraction_snapshot["sections"],
            "code_review_payloads": code_review_payloads,
            "structure_check": optional_structure_check,
            "block_placement_check_count": len(block_placement_failures),
            "block_placement_check_ids": extraction_snapshot[
                "block_placement_check_ids"
            ],
        },
    )

    fixed_sections = state.get("fixed_sections")
    is_targeted = bool(fixed_sections)

    if is_targeted:
        prior_qc_result = state.get("qc_result") or {}
        reverify_section_ids = helpers.reverify_section_ids_for_targeted(state)
        missing_checklist_ids = list(state.get("qc_missing_checklist_ids") or [])
        section_failures = list(state.get("qc_section_failures") or [])
        scoped_checklist = helpers.checklist_for_reverify(
            must_cover_checklist,
            section_ids=reverify_section_ids,
            missing_checklist_ids=missing_checklist_ids,
        )
        scoped_topic_split = helpers.topic_split_for_targets(
            topic_split,
            section_ids=reverify_section_ids,
            missing_checklist_ids=missing_checklist_ids,
            checklist=must_cover_checklist,
        )

        assert fixed_sections is not None
        prior_teaching_alignment = (
            qc_retry_verification_prompt.extract_prior_teaching_alignment_failure(
                prior_qc_result
            )
        )
        verification, verification_meta = await run_retry_verification_pass(
            teaching_instruction=teaching_instruction,
            document_outline=build_document_outline(document),
            revised_sections=fixed_sections,
            section_failures=section_failures,
            must_cover_checklist=scoped_checklist,
            topic_split=scoped_topic_split,
            domain=domain,
            prior_teaching_alignment_failure=prior_teaching_alignment,
        )
        verification_mode = "targeted"
    else:
        verification, verification_meta = await run_verification_pass(
            topic_title=topic_title,
            teaching_instruction=teaching_instruction,
            generated_content=generated_content,
            must_cover_checklist=must_cover_checklist,
            frozen_check_ids=state.get("qc_frozen_check_ids"),
            frozen_section_ids=state.get("qc_frozen_section_keys"),
            topic_split=topic_split,
            domain=domain,
        )
        verification_mode = "full"
        prior_qc_result = None
        reverify_section_ids = []
        missing_checklist_ids = []

    log_qc_agent(
        state,
        agent="qc_verification",
        pipeline_attempt=attempt,
        payload={
            **verification_meta,
            "verification": verification,
            "verification_mode": verification_mode,
            "payload_count": len(code_review_payloads),
        },
    )

    if verification is None:
        logger.warning(
            "QC verification failed on attempt %d/%d — %s",
            new_attempt,
            MAX_QC_ATTEMPTS,
            verification_meta.get("llm_error_type") or "unknown",
        )
        result = build_infra_failure_return(
            new_attempt=new_attempt,
            error_type=resolve_qc_infra_error_type(
                verification_meta.get("llm_error_type")
            ),
            extraction_snapshot=extraction_snapshot,
            provider_meta=verification_meta.get("provider_meta"),
            retry_after_seconds=verification_meta.get("retry_after_seconds"),
            next_llm_retry_at=verification_meta.get("next_llm_retry_at"),
            suggestion=verification_meta.get("suggestion"),
        )
        log_qc_agent(
            state,
            agent="qc_result",
            pipeline_attempt=attempt,
            payload={
                "qc_passed": False,
                "fail_open": False,
                "qc_inconclusive": True,
                "verification_mode": verification_mode,
                "qc_result": result["qc_result"],
            },
        )
        return result

    model_used = verification_meta.get("llm_model_used") or llm_settings.qc_llm_model

    if is_targeted and prior_qc_result is not None:
        merged_checks = merge_targeted_qc_checks(
            prior_qc_result,
            verification,
            reverify_section_ids=reverify_section_ids,
            reverify_checklist_ids=missing_checklist_ids,
            checklist=must_cover_checklist,
        )
        verification_for_build = {**verification, "checks": merged_checks}
        active_structure_checks = structure_checks
    else:
        verification_for_build = verification
        active_structure_checks = structure_checks

    qc_result = build_final_qc_result(
        verification_for_build,
        active_structure_checks,
        document=document,
        checklist=must_cover_checklist,
        model=model_used,
    )
    qc_result["verification_mode"] = verification_mode

    models_used = qc_models_used(model_used, None)

    routing = classify_retry_routing(
        qc_result,
        document,
        must_cover_checklist,
        topic_split=topic_split,
        structure_missing_ids=structure_missing_ids,
    )

    overall_status = qc_result["overall_status"]
    is_refusal = qc_result["is_refusal"]
    passed = is_qc_deliverable(
        overall_status=overall_status,
        failed_checks=qc_result.get("failed_checks") or [],
        hallucination_risk=qc_result.get("hallucination_risk", "none"),
        is_refusal=is_refusal,
        retry_recommendation=qc_result.get("retry_recommendation"),
    )

    logger.info(
        "QC attempt %d/%d — mode=%s status=%s, refusal=%s, risk=%s, checks=%d, failed=%d, retry=%s",
        new_attempt,
        MAX_QC_ATTEMPTS,
        verification_mode,
        overall_status,
        is_refusal,
        qc_result.get("hallucination_risk", "?"),
        len(qc_result.get("checks", [])),
        len(qc_result.get("failed_checks", [])),
        routing.mode,
    )

    log_qc_agent(
        state,
        agent="qc_result",
        pipeline_attempt=attempt,
        payload={
            "qc_passed": passed,
            "fail_open": False,
            "overall_status": overall_status,
            "verification_mode": verification_mode,
            "qc_retry_mode": routing.mode,
            "qc_result": qc_result,
        },
    )

    frozen_check_ids: list[str] | None = None
    frozen_section_ids: list[str] | None = None
    if not is_targeted:
        frozen_check_ids, frozen_section_ids = accumulate_frozen_sets(
            qc_result.get("checks", []),
            state.get("qc_frozen_check_ids"),
            state.get("qc_frozen_section_keys"),
        )

    if passed:
        return {
            "qc_passed": True,
            "qc_evaluated": True,
            "qc_feedback": "",
            "qc_failed_permanently": False,
            **helpers.base_qc_return(
                new_attempt=new_attempt,
                generated_content=generated_content,
                qc_result=qc_result,
                model_used=model_used,
                models_used=models_used,
                extraction_snapshot=extraction_snapshot,
                verification_mode=verification_mode,
                frozen_check_ids=frozen_check_ids,
                frozen_section_ids=frozen_section_ids,
                fixed_sections=None,
                routing_clear=True,
            ),
        }

    feedback = format_qc_feedback(qc_result)
    permanently_failed = new_attempt >= MAX_QC_ATTEMPTS

    if permanently_failed:
        logger.warning(
            "QC permanently failed after %d attempts for topic '%s'",
            MAX_QC_ATTEMPTS,
            state.get("node_title"),
        )

    return {
        "qc_passed": False,
        "qc_evaluated": True,
        "qc_feedback": feedback,
        "qc_failed_permanently": permanently_failed,
        **helpers.base_qc_return(
            new_attempt=new_attempt,
            generated_content=generated_content,
            qc_result=qc_result,
            model_used=model_used,
            models_used=models_used,
            extraction_snapshot=extraction_snapshot,
            verification_mode=verification_mode,
            frozen_check_ids=frozen_check_ids,
            frozen_section_ids=frozen_section_ids,
            fixed_sections=None,
            routing=routing,
        ),
    }
