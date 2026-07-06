# src/api/control/study_agent/nodes/quality_check_node.py
"""LangGraph QC node — deterministic checks + LLM verification + retry routing.

Pipeline position
-----------------
``study_agent`` → **quality_check** → (pass) END | (fail) ``study_agent`` retry

Each invocation increments ``qc_attempt`` (max ``MAX_QC_ATTEMPTS``).

Pass flow (two modes)
---------------------
**Full QC** (no ``fixed_sections`` in state):
  1. Deterministic extraction: structure coverage + block placement (``det_*``)
  2. ``resolve_frozen_for_full_qc`` — hash-gate frozen ids before LLM prompt
  3. ``run_verification_pass`` — full-document Groq QC
  4. ``build_final_qc_result`` — merge deterministic + LLM checks
  5. ``classify_retry_routing`` — section_patch | insert | full_regen | none
  6. ``refresh_frozen_lineage_after_qc`` — update frozen + section hashes

**Targeted QC** (``fixed_sections`` set after section patch/insert):
  1. Same deterministic checks on merged document
  2. ``run_retry_verification_pass`` — only revised sections
  3. ``merge_targeted_qc_checks`` — keep pass-1 checks for untouched sections
  4. Same routing + frozen refresh (with prune for reverify section ids)

Outputs (via ``base_qc_return`` + pass/fail fields):
  - ``qc_result``, ``qc_feedback`` (text, full_regen only), routing fields
  - ``qc_frozen_check_ids``, ``qc_frozen_section_keys``, ``qc_section_content_hashes``
"""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.runnables import RunnableConfig

from src.api.config import llm_settings
from src.api.control.study_agent.prompts.qc import qc_retry_verification_prompt
from src.api.control.study_agent.states.state import StudyMaterialGraphState
from src.api.utils.study_agent_utils.graph import node_helpers as helpers
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
from src.api.utils.study_agent_utils.quality_check_utils.core.failure_class import (
    classify_failure_class,
)
from src.api.utils.study_agent_utils.quality_check_utils.core.frozen_sets import (
    refresh_frozen_lineage_after_qc,
    resolve_frozen_for_full_qc,
)
from src.api.utils.study_agent_utils.quality_check_utils.document.document_merge import (
    build_document_outline,
)
from src.api.utils.study_agent_utils.quality_check_utils.document.targeted_merge import (
    build_carried_forward_verification,
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
from src.api.utils.study_agent_utils.quality_check_utils.infra.qc_retry_audit import (
    build_qc_result_log_payload,
)
from src.api.utils.study_agent_utils.quality_check_utils.remediation import (
    run_placement_remediation_phase,
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
from src.api.utils.study_agent_utils.quality_check_utils.verification.qc_verification_strategy import (
    checks_safe_to_carry_forward,
    decide_qc_verification,
    prior_llm_checks,
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
    """Evaluate generated study material and route failures to the study agent.

    Guards: skips QC when generation did not produce a study document, on terminal
    LLM failure, or when parsed document is missing.

    See module docstring for full vs targeted pass details.
    """
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
            payload=build_qc_result_log_payload(
                qc_result=result["qc_result"],
                routing=None,
                passed=False,
                qc_attempt=new_attempt,
                pipeline_attempt=attempt,
                qc_passed=False,
                fail_open=False,
                qc_inconclusive=True,
                verification_mode=None,
            ),
        )
        return result

    # --- Phase 1: deterministic QC (no LLM) ---
    structure = extract_structure_from_document(document)
    code_review_payloads = build_code_review_payloads(structure)
    # Single coverage computation reused by structure_check and retry_routing.
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

    # --- Phase 1b: deterministic relocation for placement failures ---
    remediation = run_placement_remediation_phase(
        document,
        domain=domain,
        checklist=must_cover_checklist,
        optional_structure_check=optional_structure_check,
        generated_content=generated_content,
    )
    document = remediation.document
    generated_content = remediation.generated_content
    block_placement_failures = remediation.block_placement_failures
    structure_checks = remediation.structure_checks
    qc_relocation_plans = remediation.qc_relocation_plans
    document_patched = remediation.document_patched
    remediation_report = remediation.remediation_report
    had_placement_remediation = remediation_report is not None

    extraction_snapshot = {
        "sections": [s.get("heading", "") for s in structure.sections],
        "code_review_payloads": code_review_payloads,
        "structure_check": optional_structure_check,
        "block_placement_checks": block_placement_failures,
        "block_placement_check_ids": [c.get("id") for c in block_placement_failures],
    }
    if had_placement_remediation and remediation_report is not None:
        extraction_snapshot["remediation"] = remediation_report.to_dict()

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

    # --- Phase 2: LLM verification (full, targeted, or deterministic carry-forward) ---
    fixed_sections = state.get("fixed_sections")
    is_targeted = bool(fixed_sections)
    prior_qc_result = state.get("qc_result")
    prior_hashes = state.get("qc_section_content_hashes") or {}
    phase1_failures = [c for c in structure_checks if not c.get("passed", True)]

    verification_decision = decide_qc_verification(
        qc_attempt=current_attempt,
        prior_qc_result=prior_qc_result,
        phase1_failures=phase1_failures,
        is_targeted=is_targeted,
        document=document,
        prior_hashes=prior_hashes,
        state_reverify_section_ids=state.get("qc_reverify_section_ids"),
    )
    verification_mode = verification_decision.mode
    verification_strategy_reason = verification_decision.reason
    phase1_failure_class = classify_failure_class(phase1_failures)
    llm_qc_skipped = False
    reverify_section_ids: list[str] = []
    missing_checklist_ids: list[str] = []
    verification: dict[str, Any] | None = None

    if verification_mode == "deterministic_only":
        assert prior_qc_result is not None
        carried_checks = checks_safe_to_carry_forward(
            prior_llm_checks(prior_qc_result),
            prior_hashes,
            document,
        )
        verification = build_carried_forward_verification(
            prior_qc_result,
            carried_checks,
        )
        verification_meta: dict[str, Any] = {
            "llm_ok": True,
            "llm_skipped": True,
            "verification_strategy_reason": verification_strategy_reason,
        }
        llm_qc_skipped = True
    elif verification_mode == "targeted":
        assert prior_qc_result is not None
        if is_targeted:
            reverify_section_ids = helpers.reverify_section_ids_for_targeted(state)
            missing_checklist_ids = list(state.get("qc_missing_checklist_ids") or [])
            revised_sections = fixed_sections
            section_failures = list(state.get("qc_section_failures") or [])
        else:
            reverify_section_ids = list(verification_decision.reverify_section_ids)
            missing_checklist_ids = list(state.get("qc_missing_checklist_ids") or [])
            reverify_set = set(reverify_section_ids)
            revised_sections = [
                section
                for section in (document.get("sections") or [])
                if isinstance(section, dict)
                and str(section.get("id", "")).strip() in reverify_set
            ]
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

        assert revised_sections is not None
        prior_teaching_alignment = (
            qc_retry_verification_prompt.extract_prior_teaching_alignment_failure(
                prior_qc_result
            )
        )
        verification, verification_meta = await run_retry_verification_pass(
            teaching_instruction=teaching_instruction,
            document_outline=build_document_outline(document),
            revised_sections=revised_sections,
            section_failures=section_failures,
            must_cover_checklist=scoped_checklist,
            topic_split=scoped_topic_split,
            domain=domain,
            prior_teaching_alignment_failure=prior_teaching_alignment,
        )
    else:
        # Hash-gate: never pass raw state frozen ids to the LLM prompt.
        frozen_check_ids, frozen_section_ids = resolve_frozen_for_full_qc(
            frozen_check_ids=state.get("qc_frozen_check_ids"),
            frozen_section_ids=state.get("qc_frozen_section_keys"),
            stored_hashes=state.get("qc_section_content_hashes"),
            document=document,
            checklist=must_cover_checklist,
        )
        verification, verification_meta = await run_verification_pass(
            topic_title=topic_title,
            teaching_instruction=teaching_instruction,
            generated_content=generated_content,
            must_cover_checklist=must_cover_checklist,
            frozen_check_ids=frozen_check_ids,
            frozen_section_ids=frozen_section_ids,
            topic_split=topic_split,
            domain=domain,
        )
        prior_qc_result = None

    log_qc_agent(
        state,
        agent="qc_verification",
        pipeline_attempt=attempt,
        payload={
            **verification_meta,
            "verification": verification,
            "verification_mode": verification_mode,
            "verification_strategy_reason": verification_strategy_reason,
            "llm_qc_skipped": llm_qc_skipped,
            "phase1_failure_class": phase1_failure_class,
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
            payload=build_qc_result_log_payload(
                qc_result=result["qc_result"],
                routing=None,
                passed=False,
                qc_attempt=new_attempt,
                pipeline_attempt=attempt,
                qc_passed=False,
                fail_open=False,
                qc_inconclusive=True,
                verification_mode=verification_mode,
                failure_class=phase1_failure_class,
                llm_qc_skipped=llm_qc_skipped,
                verification_strategy_reason=verification_strategy_reason,
            ),
        )
        return result

    model_used = (
        verification_meta.get("llm_model_used")
        or (prior_qc_result or {}).get("qc_llm_model_used")
        or llm_settings.qc_llm_model
    )

    # --- Phase 3: merge checks, score, route, refresh frozen lineage ---
    needs_targeted_merge = (
        verification_mode == "targeted"
        and prior_qc_result is not None
        and not llm_qc_skipped
    )
    if needs_targeted_merge:
        assert prior_qc_result is not None
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
        payload=build_qc_result_log_payload(
            qc_result=qc_result,
            routing=routing,
            passed=passed,
            qc_attempt=new_attempt,
            pipeline_attempt=attempt,
            qc_passed=passed,
            fail_open=False,
            overall_status=overall_status,
            verification_mode=verification_mode,
            qc_retry_mode=routing.mode,
            failure_class=routing.failure_class,
            llm_qc_skipped=llm_qc_skipped,
            verification_strategy_reason=verification_strategy_reason,
        ),
    )

    frozen_check_ids, frozen_section_ids, section_content_hashes = (
        refresh_frozen_lineage_after_qc(
            qc_result.get("checks", []),
            existing_check_ids=state.get("qc_frozen_check_ids"),
            existing_section_ids=state.get("qc_frozen_section_keys"),
            document=document,
            checklist=must_cover_checklist,
            touched_section_ids=reverify_section_ids if needs_targeted_merge else None,
            reverify_checklist_ids=missing_checklist_ids
            if needs_targeted_merge
            else None,
        )
    )

    remediation_state: dict[str, Any] = {}
    if document_patched:
        remediation_state["generation_parsed_document"] = document

    if passed:
        return {
            "qc_passed": True,
            "qc_evaluated": True,
            "qc_feedback": "",
            "qc_failed_permanently": False,
            **remediation_state,
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
                section_content_hashes=section_content_hashes,
                fixed_sections=None,
                routing_clear=True,
                qc_relocation_plans=None,
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
        **remediation_state,
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
            section_content_hashes=section_content_hashes,
            fixed_sections=None,
            routing=routing,
            qc_relocation_plans=qc_relocation_plans,
        ),
    }
