"""Deterministic relocation for block-placement QC failures."""

from src.api.utils.study_agent_utils.quality_check_utils.remediation.phase1b import (
    PlacementRemediationResult,
    relocation_plans_for_llm_fallback,
    run_placement_remediation_phase,
)
from src.api.utils.study_agent_utils.quality_check_utils.remediation.placement_patterns import (
    expand_to_equation_clause,
    find_equation_spans,
    has_high_confidence_equation_in_content,
    normalize_math,
)
from src.api.utils.study_agent_utils.quality_check_utils.remediation.relocation_apply import (
    apply_relocation_plans,
)
from src.api.utils.study_agent_utils.quality_check_utils.remediation.relocation_plan import (
    build_relocation_plans,
)
from src.api.utils.study_agent_utils.quality_check_utils.remediation.relocation_types import (
    Relocation,
    RelocationPlan,
    RemediationReport,
)

__all__ = [
    "PlacementRemediationResult",
    "Relocation",
    "RelocationPlan",
    "RemediationReport",
    "apply_relocation_plans",
    "build_relocation_plans",
    "expand_to_equation_clause",
    "find_equation_spans",
    "has_high_confidence_equation_in_content",
    "normalize_math",
    "relocation_plans_for_llm_fallback",
    "run_placement_remediation_phase",
]
