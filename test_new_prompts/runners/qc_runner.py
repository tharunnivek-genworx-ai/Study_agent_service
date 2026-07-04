"""QC verification runner — mirrors production QC node using test prompts."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from src.api.config.llm_config import llm_settings
from src.api.schemas.qc_schemas.qc_retry_routing_schema import RetryRoutingResult
from src.api.utils.LLM_utils.groq_qc_client import call_groq_qc_verification
from src.api.utils.study_agent_utils.generation.study_generation_json import (
    canonicalize_generation_json,
    parse_generation_document,
)
from src.api.utils.study_agent_utils.graph import node_helpers as helpers
from src.api.utils.study_agent_utils.quality_check_utils.checks.block_placement_checks import (
    block_placement_checks,
)
from src.api.utils.study_agent_utils.quality_check_utils.checks.deterministic import (
    build_code_review_payloads,
    extract_structure,
    structure_check,
    structure_coverage_missing_ids,
)
from src.api.utils.study_agent_utils.quality_check_utils.core.constants import (
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
from src.api.utils.study_agent_utils.quality_check_utils.results.feedback import (
    format_qc_feedback,
)
from src.api.utils.study_agent_utils.quality_check_utils.results.result_builder import (
    build_final_qc_result,
)
from src.api.utils.study_agent_utils.quality_check_utils.results.retry_routing import (
    classify_retry_routing,
)
from src.api.utils.study_agent_utils.quality_check_utils.results.scoring import (
    is_qc_deliverable,
)
from src.api.utils.study_agent_utils.quality_check_utils.verification.llm_verification import (
    run_llm_verification_pass,
)
from test_new_prompts.runners._prompt_loader import load_prompt_module
from test_new_prompts.runners._run_output import write_json, write_text
from test_new_prompts.runners._types import (
    ChecklistRunResult,
    PromptTestInputs,
    QCRunResult,
)

logger = logging.getLogger(__name__)


async def run_qc_attempt(
    *,
    run_dir: Any,
    attempt: int,
    inputs: PromptTestInputs,
    checklist: ChecklistRunResult,
    pipeline_state: dict[str, Any],
) -> QCRunResult:
    """Run one QC pass (full or targeted) using test_new_prompts/qc_verification_prompt.py."""
    output_dir = run_dir / "qc" / f"attempt_{attempt:02d}"
    output_dir.mkdir(parents=True, exist_ok=True)
    started_at = datetime.now(UTC)

    if not helpers.groq_api_keys_configured():
        error = "No GROQ API keys are configured."
        write_json(output_dir / "metadata.json", {"ok": False, "error": error})
        return QCRunResult(
            ok=False,
            output_dir=output_dir,
            attempt=attempt,
            error=error,
        )

    generated_content = (pipeline_state.get("generated_content") or "").strip()
    if not generated_content:
        error = "No generated content available for QC."
        write_json(output_dir / "metadata.json", {"ok": False, "error": error})
        return QCRunResult(
            ok=False,
            output_dir=output_dir,
            attempt=attempt,
            error=error,
        )

    domain = checklist.domain
    must_cover_checklist = checklist.must_cover_checklist
    topic_split = checklist.topic_split
    fixed_sections = pipeline_state.get("fixed_sections")
    is_targeted = bool(fixed_sections)

    try:
        canonical_content = canonicalize_generation_json(generated_content)
    except ValueError as exc:
        error = f"Invalid JSON document for QC: {exc}"
        write_json(output_dir / "metadata.json", {"ok": False, "error": error})
        return QCRunResult(
            ok=False,
            output_dir=output_dir,
            attempt=attempt,
            error=error,
        )

    document = parse_generation_document(canonical_content) or {}
    structure = extract_structure(canonical_content)
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
    }
    write_json(output_dir / "extraction_snapshot.json", extraction_snapshot)

    qc_verification_prompt = load_prompt_module("qc_verification_prompt")
    qc_retry_prompt = load_prompt_module("qc_retry_verification_prompt")

    if is_targeted:
        prior_qc_result = pipeline_state.get("qc_result") or {}
        reverify_section_ids = helpers.reverify_section_ids_for_targeted(pipeline_state)  # type: ignore[arg-type]
        missing_checklist_ids = list(
            pipeline_state.get("qc_missing_checklist_ids") or []
        )
        section_failures = list(pipeline_state.get("qc_section_failures") or [])
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

        retry_system = qc_retry_prompt.build_system_prompt(domain=domain or None)
        retry_user = qc_retry_prompt.build_user_message(
            teaching_instruction=inputs.effective_instruction,
            document_outline=build_document_outline(document),
            revised_sections=fixed_sections,
            section_failures=section_failures,
            must_cover_checklist=scoped_checklist,
            topic_split=scoped_topic_split,
            domain=domain,
        )
        write_text(output_dir / "system_prompt.txt", retry_system)
        write_text(output_dir / "user_message.txt", retry_user)

        verification, verification_meta = await run_llm_verification_pass(
            build_user_message=qc_retry_prompt.build_user_message,
            system_prompt=qc_retry_prompt.build_system_prompt(domain=domain or None),
            reprompt_system=qc_retry_prompt.REPROMPT_SYSTEM,
            call_llm=call_groq_qc_verification,
            graph_node="qc_retry_verification",
            model_setting=llm_settings.qc_llm_model,
            user_message_kwargs={
                "teaching_instruction": inputs.effective_instruction,
                "document_outline": build_document_outline(document),
                "revised_sections": fixed_sections,
                "section_failures": section_failures,
                "must_cover_checklist": scoped_checklist,
                "topic_split": scoped_topic_split,
                "domain": domain,
            },
            pass_label="QC targeted verification",
        )
        verification_mode = "targeted"
    else:
        system_prompt = qc_verification_prompt.build_system_prompt(
            domain=domain or None
        )
        user_message = qc_verification_prompt.build_user_message(
            topic_title=inputs.topic,
            teaching_instruction=inputs.effective_instruction,
            generated_content=canonical_content,
            must_cover_checklist=must_cover_checklist,
            frozen_check_ids=pipeline_state.get("qc_frozen_check_ids"),
            frozen_section_ids=pipeline_state.get("qc_frozen_section_keys"),
            topic_split=topic_split,
            domain=domain,
            max_doc_chars=llm_settings.qc_document_max_chars,
        )
        write_text(output_dir / "system_prompt.txt", system_prompt)
        write_text(output_dir / "user_message.txt", user_message)

        verification, verification_meta = await run_llm_verification_pass(
            build_user_message=qc_verification_prompt.build_user_message,
            system_prompt=system_prompt,
            reprompt_system=qc_verification_prompt.REPROMPT_SYSTEM,
            call_llm=call_groq_qc_verification,
            graph_node="qc_verification",
            model_setting=llm_settings.qc_llm_model,
            user_message_kwargs={
                "topic_title": inputs.topic,
                "teaching_instruction": inputs.effective_instruction,
                "generated_content": canonical_content,
                "must_cover_checklist": must_cover_checklist,
                "frozen_check_ids": pipeline_state.get("qc_frozen_check_ids"),
                "frozen_section_ids": pipeline_state.get("qc_frozen_section_keys"),
                "topic_split": topic_split,
                "domain": domain,
                "max_doc_chars": llm_settings.qc_document_max_chars,
            },
            pass_label="QC verification",
        )
        verification_mode = "full"
        prior_qc_result = None
        reverify_section_ids = []
        missing_checklist_ids = []

    finished_at = datetime.now(UTC)
    metadata: dict[str, Any] = {
        "stage": "qc",
        "attempt": attempt,
        "verification_mode": verification_mode,
        "topic": inputs.topic,
        "domain": domain,
        "started_at": started_at.isoformat(),
        "finished_at": finished_at.isoformat(),
        "duration_seconds": (finished_at - started_at).total_seconds(),
        **verification_meta,
    }

    raw_response = verification_meta.get("raw_response")
    if raw_response:
        write_text(output_dir / "raw_response.json", raw_response)

    if verification is not None:
        write_json(output_dir / "parsed_verification.json", verification)

    if not verification_meta.get("llm_ok"):
        metadata["ok"] = False
        metadata["error"] = verification_meta.get("llm_error_type") or "LLM call failed"
        write_json(output_dir / "metadata.json", metadata)
        return QCRunResult(
            ok=False,
            output_dir=output_dir,
            attempt=attempt,
            verification_mode=verification_mode,
            metadata=metadata,
            error=metadata["error"],
        )

    if verification is None:
        metadata["ok"] = False
        metadata["error"] = "Failed to parse QC verification JSON"
        write_json(output_dir / "metadata.json", metadata)
        return QCRunResult(
            ok=False,
            output_dir=output_dir,
            attempt=attempt,
            verification_mode=verification_mode,
            metadata=metadata,
            error=metadata["error"],
        )

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

    model_used = verification_meta.get("llm_model_used") or llm_settings.qc_llm_model
    qc_result = build_final_qc_result(
        verification_for_build,
        active_structure_checks,
        document=document,
        checklist=must_cover_checklist,
        model=model_used,
    )
    qc_result["verification_mode"] = verification_mode
    write_json(output_dir / "qc_result.json", qc_result)

    routing: RetryRoutingResult = classify_retry_routing(
        qc_result,
        document,
        must_cover_checklist,
        topic_split=topic_split,
        structure_missing_ids=structure_missing_ids,
    )
    write_json(
        output_dir / "retry_routing.json",
        {
            "mode": routing.mode,
            "failed_section_ids": routing.failed_section_ids,
            "missing_checklist_ids": routing.missing_checklist_ids,
            "section_failures": routing.section_failures,
            "rationale": routing.rationale,
        },
    )

    passed = is_qc_deliverable(
        overall_status=qc_result["overall_status"],
        failed_checks=qc_result.get("failed_checks") or [],
        hallucination_risk=qc_result.get("hallucination_risk", "none"),
        is_refusal=bool(qc_result.get("is_refusal")),
        retry_recommendation=qc_result.get("retry_recommendation"),
    )
    permanently_failed = attempt >= MAX_QC_ATTEMPTS and not passed
    feedback = "" if passed else format_qc_feedback(qc_result)

    frozen_check_ids: list[str] | None = None
    frozen_section_ids: list[str] | None = None
    if not is_targeted:
        frozen_check_ids, frozen_section_ids = accumulate_frozen_sets(
            qc_result.get("checks", []),
            pipeline_state.get("qc_frozen_check_ids"),
            pipeline_state.get("qc_frozen_section_keys"),
        )

    failed_count = len(qc_result.get("failed_checks") or [])
    check_count = len(qc_result.get("checks") or [])

    metadata.update(
        {
            "ok": True,
            "qc_passed": passed,
            "qc_failed_permanently": permanently_failed,
            "overall_status": qc_result.get("overall_status"),
            "hallucination_risk": qc_result.get("hallucination_risk"),
            "retry_mode": routing.mode,
            "checks_total": check_count,
            "checks_failed": failed_count,
            "frozen_check_ids": frozen_check_ids,
            "frozen_section_ids": frozen_section_ids,
        }
    )
    write_json(output_dir / "metadata.json", metadata)

    logger.info(
        "QC attempt %d/%d — mode=%s status=%s passed=%s retry=%s failed=%d/%d",
        attempt,
        MAX_QC_ATTEMPTS,
        verification_mode,
        qc_result.get("overall_status"),
        passed,
        routing.mode,
        failed_count,
        check_count,
    )

    return QCRunResult(
        ok=True,
        output_dir=output_dir,
        attempt=attempt,
        qc_passed=passed,
        qc_failed_permanently=permanently_failed,
        qc_result=qc_result,
        routing=routing,
        qc_feedback=feedback,
        verification_mode=verification_mode,
        frozen_check_ids=frozen_check_ids,
        frozen_section_ids=frozen_section_ids,
        metadata=metadata,
    )
