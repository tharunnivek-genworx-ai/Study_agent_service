"""Quality-check utilities for study material generation."""

from src.api.schemas.qc_schemas.qc_check_schema import (
    CODE_CATEGORIES,
    PROSE_CATEGORIES,
    VERIFICATION_CATEGORIES,
    is_valid_qc_verification_response,
)
from src.api.schemas.qc_schemas.qc_retry_routing_schema import (
    RetryMode,
    RetryRoutingResult,
)
from src.api.utils.study_agent_utils.quality_check_utils.checks.deterministic import (
    CodeArtifact,
    DocumentStructure,
    attach_code_artifact_ids_from_document,
    build_code_review_payloads,
    extract_structure,
    structure_check,
)
from src.api.utils.study_agent_utils.quality_check_utils.checks.skip_rules import (
    should_skip_qc,
)
from src.api.utils.study_agent_utils.quality_check_utils.core.constants import (
    DEFAULT_INSTRUCTION,
    FROZEN_SECTION_CATEGORIES,
    MAX_QC_ATTEMPTS,
    MAX_VERIFICATION_PARSE_RETRIES,
)
from src.api.utils.study_agent_utils.quality_check_utils.core.frozen_sets import (
    accumulate_frozen_sets,
)
from src.api.utils.study_agent_utils.quality_check_utils.document.document_merge import (
    MergePatchesResult,
    build_document_outline,
    extract_sections_by_ids,
    insert_sections,
    merge_section_patches,
)
from src.api.utils.study_agent_utils.quality_check_utils.document.document_prep import (
    prepare_document_for_qc,
)
from src.api.utils.study_agent_utils.quality_check_utils.document.targeted_merge import (
    check_targets_reverify,
    merge_targeted_qc_checks,
)
from src.api.utils.study_agent_utils.quality_check_utils.infra.artifact_logging import (
    log_qc_agent,
    pipeline_attempt,
)
from src.api.utils.study_agent_utils.quality_check_utils.infra.infra_failure import (
    build_infra_failure_return,
)
from src.api.utils.study_agent_utils.quality_check_utils.parsing.json_parse import (
    parse_llm_json_object,
    parse_qc_verification_response,
)
from src.api.utils.study_agent_utils.quality_check_utils.results.feedback import (
    format_qc_feedback,
)
from src.api.utils.study_agent_utils.quality_check_utils.results.node_returns import (
    build_invalid_json_return,
    build_skip_return,
)
from src.api.utils.study_agent_utils.quality_check_utils.results.result_builder import (
    build_final_qc_result,
    qc_models_used,
    split_verification_checks,
)
from src.api.utils.study_agent_utils.quality_check_utils.results.retry_routing import (
    classify_retry_routing,
)
from src.api.utils.study_agent_utils.quality_check_utils.results.scoring import (
    derive_overall_status,
    derive_scores,
    extract_failed_checks,
    public_scores,
)
from src.api.utils.study_agent_utils.quality_check_utils.verification.llm_verification import (
    run_llm_verification_pass,
)
from src.api.utils.study_agent_utils.quality_check_utils.verification.verification_pass import (
    run_retry_verification_pass,
    run_verification_pass,
)

__all__ = [
    "CODE_CATEGORIES",
    "CodeArtifact",
    "DEFAULT_INSTRUCTION",
    "DocumentStructure",
    "FROZEN_SECTION_CATEGORIES",
    "MAX_QC_ATTEMPTS",
    "MAX_VERIFICATION_PARSE_RETRIES",
    "MergePatchesResult",
    "PROSE_CATEGORIES",
    "RetryMode",
    "RetryRoutingResult",
    "VERIFICATION_CATEGORIES",
    "accumulate_frozen_sets",
    "attach_code_artifact_ids_from_document",
    "build_code_review_payloads",
    "build_document_outline",
    "build_final_qc_result",
    "build_infra_failure_return",
    "build_invalid_json_return",
    "build_skip_return",
    "check_targets_reverify",
    "classify_retry_routing",
    "derive_overall_status",
    "derive_scores",
    "extract_failed_checks",
    "extract_sections_by_ids",
    "extract_structure",
    "format_qc_feedback",
    "insert_sections",
    "is_valid_qc_verification_response",
    "log_qc_agent",
    "merge_section_patches",
    "merge_targeted_qc_checks",
    "parse_llm_json_object",
    "parse_qc_verification_response",
    "pipeline_attempt",
    "prepare_document_for_qc",
    "public_scores",
    "qc_models_used",
    "run_llm_verification_pass",
    "run_retry_verification_pass",
    "run_verification_pass",
    "should_skip_qc",
    "split_verification_checks",
    "structure_check",
]
