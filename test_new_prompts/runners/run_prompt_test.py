"""End-to-end prompt test runner: concept checklist → generation → QC retry loop.

Edit test_inputs.py with your topic and effective instruction, then run:

    cd study_agent_service
    python -m test_new_prompts.runners.run_prompt_test

Outputs are written to test_new_prompts/run_output/{topic_slug}_{timestamp}/.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from datetime import UTC, datetime
from typing import Any

from src.api.utils.study_agent_utils.graph import node_helpers as helpers
from src.api.utils.study_agent_utils.quality_check_utils.core.constants import (
    MAX_QC_ATTEMPTS,
)
from test_new_prompts.runners import test_inputs
from test_new_prompts.runners._paths import SERVICE_ROOT
from test_new_prompts.runners._pipeline_state import make_pipeline_state
from test_new_prompts.runners._run_output import create_run_dir, write_run_manifest
from test_new_prompts.runners._types import PromptTestInputs, PromptTestRun
from test_new_prompts.runners.concept_checklist_runner import run_concept_checklist
from test_new_prompts.runners.generation_runner import run_generation
from test_new_prompts.runners.qc_runner import run_qc_attempt
from test_new_prompts.runners.retry_runner import run_retry

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)


def _ensure_service_root_on_path() -> None:
    service_root = str(SERVICE_ROOT)
    if service_root not in sys.path:
        sys.path.insert(0, service_root)


def load_inputs() -> PromptTestInputs:
    topic = (test_inputs.TOPIC or "").strip()
    instruction = (test_inputs.EFFECTIVE_INSTRUCTION or "").strip()
    if not topic:
        raise ValueError("Set TOPIC in test_new_prompts/runners/test_inputs.py")
    if not instruction:
        raise ValueError(
            "Set EFFECTIVE_INSTRUCTION in test_new_prompts/runners/test_inputs.py"
        )
    return PromptTestInputs(topic=topic, effective_instruction=instruction)


def _apply_qc_to_state(
    pipeline_state: dict,
    qc_result: Any,
) -> None:
    """Update pipeline state after a QC attempt (mirrors graph node return fields)."""
    pipeline_state["qc_attempt"] = qc_result.attempt
    pipeline_state["qc_passed"] = qc_result.qc_passed
    pipeline_state["qc_result"] = qc_result.qc_result
    pipeline_state["qc_feedback"] = qc_result.qc_feedback
    pipeline_state["fixed_sections"] = None

    if qc_result.qc_passed:
        pipeline_state.update(helpers.routing_state(clear=True))
        return

    if qc_result.routing:
        pipeline_state.update(helpers.routing_state(qc_result.routing))
    if qc_result.frozen_check_ids is not None:
        pipeline_state["qc_frozen_check_ids"] = qc_result.frozen_check_ids
    if qc_result.frozen_section_ids is not None:
        pipeline_state["qc_frozen_section_keys"] = qc_result.frozen_section_ids
    if qc_result.section_content_hashes is not None:
        pipeline_state["qc_section_content_hashes"] = qc_result.section_content_hashes


def _apply_retry_to_state(
    pipeline_state: dict,
    retry_result: Any,
) -> None:
    pipeline_state["generated_content"] = retry_result.generated_content or ""
    pipeline_state["fixed_sections"] = retry_result.fixed_sections


async def run_full_pipeline(inputs: PromptTestInputs) -> PromptTestRun:
    started_at = datetime.now(UTC)
    run_dir, topic_slug, timestamp = create_run_dir(inputs.topic, started_at)

    logger.info("Starting prompt test run: %s", run_dir.name)
    logger.info("Topic: %s", inputs.topic)

    run = PromptTestRun(
        run_dir=run_dir,
        topic_slug=topic_slug,
        timestamp=timestamp,
        started_at=started_at,
        inputs=inputs,
    )

    checklist = await run_concept_checklist(run_dir=run_dir, inputs=inputs)
    run.checklist = checklist
    if not checklist.ok:
        run.final_status = "failed_concept_checklist"
        _write_manifest(run, started_at)
        return run

    generation = await run_generation(
        run_dir=run_dir, inputs=inputs, checklist=checklist
    )
    run.generation = generation
    if not generation.ok or not generation.generated_content:
        run.final_status = "failed_generation"
        _write_manifest(run, started_at)
        return run

    pipeline_state = make_pipeline_state(
        inputs=inputs,
        checklist=checklist,
        generated_content=generation.generated_content,
    )

    for attempt in range(1, MAX_QC_ATTEMPTS + 1):
        qc = await run_qc_attempt(
            run_dir=run_dir,
            attempt=attempt,
            inputs=inputs,
            checklist=checklist,
            pipeline_state=pipeline_state,
        )
        run.qc_attempts.append(qc)

        if not qc.ok:
            run.final_status = f"failed_qc_attempt_{attempt:02d}"
            _write_manifest(run, started_at)
            return run

        _apply_qc_to_state(pipeline_state, qc)

        if qc.qc_passed:
            run.final_qc_passed = True
            run.final_status = "qc_passed"
            _write_manifest(run, started_at)
            return run

        if qc.qc_failed_permanently or attempt >= MAX_QC_ATTEMPTS:
            run.final_status = "qc_failed_permanently"
            _write_manifest(run, started_at)
            return run

        retry_mode = pipeline_state.get("qc_retry_mode") or "none"
        if retry_mode == "none":
            run.final_status = "qc_failed_no_retry_mode"
            _write_manifest(run, started_at)
            return run

        retry = await run_retry(
            run_dir=run_dir,
            attempt=attempt,
            retry_mode=retry_mode,
            inputs=inputs,
            checklist=checklist,
            pipeline_state=pipeline_state,
        )
        run.retries.append(retry)

        if not retry.ok or not retry.generated_content:
            run.final_status = f"failed_retry_attempt_{attempt:02d}"
            _write_manifest(run, started_at)
            return run

        _apply_retry_to_state(pipeline_state, retry)

    run.final_status = "exhausted_qc_attempts"
    _write_manifest(run, started_at)
    return run


def _write_manifest(run: PromptTestRun, started_at: datetime) -> None:
    finished_at = datetime.now(UTC)
    last_qc = run.qc_attempts[-1] if run.qc_attempts else None
    last_retry = run.retries[-1] if run.retries else None

    write_run_manifest(
        run.run_dir,
        topic=run.inputs.topic,
        topic_slug=run.topic_slug,
        timestamp=run.timestamp,
        started_at=started_at,
        finished_at=finished_at,
        generation_dir=run.generation.output_dir
        if run.generation
        else run.run_dir / "generation",
        qc_dir=last_qc.output_dir if last_qc else run.run_dir / "qc",
        extra={
            "status": run.final_status,
            "final_qc_passed": run.final_qc_passed,
            "qc_attempts": len(run.qc_attempts),
            "retry_attempts": len(run.retries),
            "concept_checklist_output_dir": str(run.checklist.output_dir)
            if run.checklist
            else None,
            "last_retry_mode": last_retry.retry_mode if last_retry else None,
            "last_retry_output_dir": str(last_retry.output_dir) if last_retry else None,
            "last_qc_overall_status": (
                last_qc.qc_result.get("overall_status")
                if last_qc and last_qc.qc_result
                else None
            ),
            "last_qc_retry_mode": (
                last_qc.routing.mode if last_qc and last_qc.routing else None
            ),
            "domain": run.checklist.domain if run.checklist else None,
            "topic_split_count": len(run.checklist.topic_split) if run.checklist else 0,
            "must_cover_count": len(run.checklist.must_cover_checklist)
            if run.checklist
            else 0,
        },
    )


def _print_summary(run: PromptTestRun) -> int:
    print("\n=== Prompt test run summary ===")
    print(f"Run folder: {run.run_dir}")
    print(f"Final status: {run.final_status}")

    if run.checklist:
        status = "OK" if run.checklist.ok else "FAILED"
        print(f"Concept checklist: {status}")

    if run.generation:
        status = "OK" if run.generation.ok else "FAILED"
        print(f"Initial generation: {status}")

    for qc in run.qc_attempts:
        mode = qc.verification_mode or "?"
        routing = qc.routing.mode if qc.routing else "none"
        if qc.qc_passed:
            verdict = "PASSED"
        elif not qc.ok:
            verdict = "ERROR"
        else:
            verdict = "FAILED"
        checks = qc.qc_result.get("checks") if qc.qc_result else []
        failed = sum(1 for c in (checks or []) if not c.get("passed"))
        total = len(checks or [])
        print(
            f"QC attempt {qc.attempt:02d} ({mode}): {verdict} "
            f"— {total - failed}/{total} checks passed, retry={routing}"
        )
        if qc.qc_result:
            print(
                f"  overall_status={qc.qc_result.get('overall_status')}, "
                f"hallucination_risk={qc.qc_result.get('hallucination_risk')}"
            )

    for retry in run.retries:
        status = "OK" if retry.ok else "FAILED"
        print(f"Retry attempt {retry.attempt:02d} ({retry.retry_mode}): {status}")

    success = run.final_qc_passed
    return 0 if success else 1


async def main_async() -> int:
    _ensure_service_root_on_path()
    run = await run_full_pipeline(load_inputs())
    return _print_summary(run)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Run concept checklist, generation, QC, and QC-driven retries "
            f"(up to {MAX_QC_ATTEMPTS} QC attempts)."
        )
    )
    parser.parse_args()
    raise SystemExit(asyncio.run(main_async()))


if __name__ == "__main__":
    main()
