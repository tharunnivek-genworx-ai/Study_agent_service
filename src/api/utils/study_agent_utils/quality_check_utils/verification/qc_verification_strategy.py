"""QC verification strategy — decide full vs targeted vs deterministic-only LLM pass.

After substance is certified on a prior QC pass, skip the full-document Groq call when
only placement (``det_*``) failures remain and section hashes are unchanged. Hash-gated
carry-forward reuses prior LLM checks; changed sections trigger targeted re-verify only.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from src.api.utils.study_agent_utils.quality_check_utils.core.failure_class import (
    is_placement_only_failure,
)
from src.api.utils.study_agent_utils.quality_check_utils.core.frozen_sets import (
    build_section_hashes,
)

QcVerificationMode = Literal["full", "targeted", "deterministic_only"]

_SUBSTANCE_CATEGORIES = frozenset(
    {"must_cover", "content_accuracy", "teaching_alignment"}
)


@dataclass(frozen=True)
class QcVerificationDecision:
    mode: QcVerificationMode
    reason: str
    reverify_section_ids: list[str]


def _is_llm_check(check: dict[str, Any]) -> bool:
    check_id = str(check.get("id", ""))
    if check_id.startswith("det_"):
        return False
    return str(check.get("category", "")) != "structure"


def substance_certified(prior_qc_result: dict[str, Any] | None) -> bool:
    """True when prior pass had no failed must_cover, content_accuracy, or teaching_alignment."""
    if not prior_qc_result:
        return False
    for check in prior_qc_result.get("checks") or []:
        if not isinstance(check, dict):
            continue
        if str(check.get("category", "")) not in _SUBSTANCE_CATEGORIES:
            continue
        if not check.get("passed", True):
            return False
    return True


def _section_hash_unchanged(
    section_id: str,
    *,
    prior_hashes: dict[str, str],
    current_hashes: dict[str, str],
) -> bool:
    baseline = prior_hashes.get(section_id)
    if baseline is None:
        return False
    current = current_hashes.get(section_id)
    return current is not None and current == baseline


def checks_safe_to_carry_forward(
    prior_checks: list[dict[str, Any]],
    prior_hashes: dict[str, str],
    document: dict[str, Any],
) -> list[dict[str, Any]]:
    """Return prior LLM checks whose section scope still matches stored content hashes."""
    if not prior_hashes:
        return []
    current_hashes = build_section_hashes(document)
    safe: list[dict[str, Any]] = []
    for check in prior_checks:
        if not isinstance(check, dict):
            continue
        section_id = str(check.get("section_id", "") or "").strip()
        if section_id:
            if _section_hash_unchanged(
                section_id,
                prior_hashes=prior_hashes,
                current_hashes=current_hashes,
            ):
                safe.append(check)
            continue
        if all(
            _section_hash_unchanged(
                sid,
                prior_hashes=prior_hashes,
                current_hashes=current_hashes,
            )
            for sid in prior_hashes
        ):
            safe.append(check)
    return safe


def section_ids_from_failures(failures: list[dict[str, Any]]) -> list[str]:
    """Unique section ids referenced by failed deterministic checks."""
    ids: set[str] = set()
    for check in failures:
        section_id = str(check.get("section_id", "") or "").strip()
        if section_id:
            ids.add(section_id)
    return sorted(ids)


def sections_with_changed_hashes(
    prior_hashes: dict[str, str],
    document: dict[str, Any],
    *,
    focus_section_ids: list[str] | None = None,
) -> list[str]:
    """Section ids whose content hash differs from the prior QC baseline."""
    if not prior_hashes:
        return list(focus_section_ids or [])
    current_hashes = build_section_hashes(document)
    ids_to_check = focus_section_ids if focus_section_ids else list(current_hashes)
    changed: list[str] = []
    for section_id in ids_to_check:
        sid = str(section_id).strip()
        if not sid:
            continue
        if not _section_hash_unchanged(
            sid,
            prior_hashes=prior_hashes,
            current_hashes=current_hashes,
        ):
            changed.append(sid)
    return sorted(changed)


def decide_qc_verification(
    *,
    qc_attempt: int,
    prior_qc_result: dict[str, Any] | None,
    phase1_failures: list[dict[str, Any]],
    is_targeted: bool,
    document: dict[str, Any],
    prior_hashes: dict[str, str] | None,
    state_reverify_section_ids: list[str] | None = None,
) -> QcVerificationDecision:
    """Choose full, targeted, or deterministic-only verification for this QC visit."""
    if is_targeted:
        reverify = list(state_reverify_section_ids or [])
        return QcVerificationDecision(
            mode="targeted",
            reason="fixed_sections set for section patch/insert retry",
            reverify_section_ids=reverify,
        )

    if qc_attempt == 0:
        return QcVerificationDecision(
            mode="full",
            reason="first QC pass — establish substance baseline",
            reverify_section_ids=[],
        )

    if not substance_certified(prior_qc_result):
        return QcVerificationDecision(
            mode="full",
            reason="prior substance checks not certified",
            reverify_section_ids=[],
        )

    if phase1_failures and not is_placement_only_failure(phase1_failures):
        return QcVerificationDecision(
            mode="full",
            reason="substance or mixed deterministic failures",
            reverify_section_ids=[],
        )

    focus_ids = section_ids_from_failures(phase1_failures)
    changed = sections_with_changed_hashes(
        prior_hashes or {},
        document,
        focus_section_ids=focus_ids or None,
    )
    if changed:
        return QcVerificationDecision(
            mode="targeted",
            reason="placement failures on sections with changed content hashes",
            reverify_section_ids=changed,
        )

    return QcVerificationDecision(
        mode="deterministic_only",
        reason="placement-only or clear phase1; prior substance certified; hashes stable",
        reverify_section_ids=[],
    )


def prior_llm_checks(prior_qc_result: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Extract LLM-emitted checks from a prior ``qc_result`` (excludes ``det_*``)."""
    if not prior_qc_result:
        return []
    return [
        check
        for check in (prior_qc_result.get("checks") or [])
        if isinstance(check, dict) and _is_llm_check(check)
    ]


__all__ = [
    "QcVerificationDecision",
    "QcVerificationMode",
    "checks_safe_to_carry_forward",
    "decide_qc_verification",
    "prior_llm_checks",
    "section_ids_from_failures",
    "sections_with_changed_hashes",
    "substance_certified",
]
