# tests/test_quality_check_merge.py
"""Unit tests for quality_check_node merge helpers."""

from __future__ import annotations

from src.api.utils.study_agent_utils.generation.study_generation_json import (
    normalize_must_cover_section_ids,
)
from src.api.utils.study_agent_utils.quality_check_utils.core.frozen_sets import (
    accumulate_frozen_sets,
)
from src.api.utils.study_agent_utils.quality_check_utils.document.targeted_merge import (
    check_targets_reverify,
    merge_targeted_qc_checks,
)
from src.api.utils.study_agent_utils.quality_check_utils.results.result_builder import (
    build_final_qc_result,
    dedup_document_level_checks,
    qc_models_used,
)
from src.api.utils.study_agent_utils.quality_check_utils.results.scoring import (
    derive_overall_status,
    extract_failed_checks,
    is_qc_deliverable,
)

_SAMPLE_DOC = {
    "sections": [
        {"id": "mc_1", "heading": "Introduction", "content": "Intro only."},
        {
            "id": "mc_2",
            "heading": "Examples",
            "content": "Example prose.",
            "code_blocks": [{"language": "python", "code": "pass"}],
        },
    ]
}


class TestBuildFinalQcResult:
    def test_is_refusal_true_when_verification_refuses(self):
        result = build_final_qc_result(
            {
                "is_refusal": True,
                "hallucination_risk": "none",
                "issues": [],
                "checks": [],
            },
            [],
            document=_SAMPLE_DOC,
            checklist=[],
            model="llama-3.3-70b-versatile",
        )
        assert result["is_refusal"] is True
        assert result["overall_status"] == "pass"

    def test_is_refusal_false_when_verification_does_not_refuse(self):
        result = build_final_qc_result(
            {
                "is_refusal": False,
                "hallucination_risk": "none",
                "issues": [],
                "checks": [
                    {
                        "id": "c1",
                        "category": "content_accuracy",
                        "passed": False,
                        "severity": "critical",
                    }
                ],
            },
            [],
            document=_SAMPLE_DOC,
            checklist=[],
            model="llama-3.3-70b-versatile",
        )
        assert result["is_refusal"] is False
        assert result["overall_status"] == "fail"

    def test_qc_models_used_in_result(self):
        result = build_final_qc_result(
            {
                "is_refusal": False,
                "hallucination_risk": "none",
                "issues": [],
                "checks": [],
            },
            [],
            document=_SAMPLE_DOC,
            checklist=[],
            model="llama-3.3-70b-versatile",
        )
        assert result["qc_llm_models_used"] == {
            "prose": "llama-3.3-70b-versatile",
            "code": None,
        }


class TestAccumulateFrozenSets:
    def test_accumulates_passed_must_cover_and_code_checks(self):
        checks = [
            {
                "category": "must_cover",
                "passed": True,
                "checklist_id": "mc_1",
            },
            {
                "category": "must_cover",
                "passed": False,
                "checklist_id": "mc_2",
            },
            {
                "category": "code_quality",
                "passed": True,
                "section_id": "mc_2",
            },
            {
                "category": "stack_fidelity",
                "passed": True,
                "section_id": "mc_3",
            },
            {
                "category": "content_accuracy",
                "passed": True,
                "section_id": "mc_1",
            },
        ]
        check_ids, section_ids = accumulate_frozen_sets(checks, None, None)
        assert check_ids == ["mc_1"]
        assert section_ids == ["mc_2", "mc_3"]

    def test_merges_with_existing_frozen_sets(self):
        checks = [
            {
                "category": "must_cover",
                "passed": True,
                "checklist_id": "mc_2",
            },
            {
                "category": "code_quality",
                "passed": True,
                "section_id": "mc_4",
            },
        ]
        check_ids, section_ids = accumulate_frozen_sets(
            checks,
            ["mc_1"],
            ["mc_2"],
        )
        assert check_ids == ["mc_1", "mc_2"]
        assert section_ids == ["mc_2", "mc_4"]

    def test_empty_checks_preserves_existing(self):
        check_ids, section_ids = accumulate_frozen_sets(
            [],
            ["mc_1"],
            ["mc_2"],
        )
        assert check_ids == ["mc_1"]
        assert section_ids == ["mc_2"]


class TestQcModelsUsed:
    def test_builds_prose_and_code_keys(self):
        assert qc_models_used("a", "b") == {"prose": "a", "code": "b"}
        assert qc_models_used("a", None) == {"prose": "a", "code": None}


class TestUnifiedVerificationMerge:
    def test_attaches_section_id_from_document_code_blocks(self):
        verification = {
            "is_refusal": False,
            "hallucination_risk": "none",
            "issues": [],
            "checks": [
                {
                    "id": "mc_1",
                    "category": "must_cover",
                    "checklist_id": "mc_1",
                    "passed": True,
                    "severity": "critical",
                },
                {
                    "id": "code_quality_1",
                    "category": "code_quality",
                    "code_artifact_id": "code_1",
                    "passed": False,
                    "severity": "critical",
                },
            ],
        }
        result = build_final_qc_result(
            verification,
            [],
            document=_SAMPLE_DOC,
            checklist=[{"id": "mc_1", "concept": "Intro", "priority": "required"}],
            model="llama-3.3-70b-versatile",
        )
        code_check = next(
            c for c in result["checks"] if c.get("category") == "code_quality"
        )
        assert code_check["section_id"] == "mc_2"
        assert result["qc_llm_models_used"]["code"] is None

    def test_normalizes_empty_must_cover_section_id_from_checklist(self):
        verification = {
            "is_refusal": False,
            "hallucination_risk": "none",
            "issues": [],
            "checks": [
                {
                    "id": "mc_4",
                    "category": "must_cover",
                    "checklist_id": "mc_4",
                    "section_id": "",
                    "passed": False,
                    "severity": "critical",
                }
            ],
        }
        checklist = [
            {
                "id": "mc_4",
                "section_id": "ts_2",
                "concept": "Substituents",
                "priority": "required",
            }
        ]
        result = build_final_qc_result(
            verification,
            [],
            document=_SAMPLE_DOC,
            checklist=checklist,
            model="llama-3.3-70b-versatile",
        )
        must_cover = next(
            c for c in result["checks"] if c.get("category") == "must_cover"
        )
        assert must_cover["section_id"] == "ts_2"

    def test_corrects_wrong_must_cover_section_id_from_checklist(self):
        verification = {
            "is_refusal": False,
            "hallucination_risk": "none",
            "issues": [],
            "checks": [
                {
                    "id": "mc_2",
                    "category": "must_cover",
                    "checklist_id": "mc_2",
                    "section_id": "ts_3",
                    "passed": False,
                    "severity": "critical",
                }
            ],
        }
        checklist = [
            {
                "id": "mc_2",
                "section_id": "ts_2",
                "concept": "Limits",
                "priority": "required",
            }
        ]
        result = build_final_qc_result(
            verification,
            [],
            document=_SAMPLE_DOC,
            checklist=checklist,
            model="llama-3.3-70b-versatile",
        )
        must_cover = next(
            c for c in result["checks"] if c.get("category") == "must_cover"
        )
        assert must_cover["section_id"] == "ts_2"

    def test_scores_exclude_internal_routing_dimensions(self):
        structure_checks = [
            {
                "id": "det_structure_coverage",
                "category": "structure",
                "passed": False,
                "severity": "critical",
            }
        ]
        result = build_final_qc_result(
            {
                "is_refusal": False,
                "hallucination_risk": "none",
                "issues": [],
                "checks": [],
            },
            structure_checks,
            document=_SAMPLE_DOC,
            checklist=[],
            model="llama-3.3-70b-versatile",
        )
        assert "structure" not in result["scores"]
        assert "readability" not in result["scores"]

    def test_teaching_alignment_evicted_when_sections_revised(self):
        prior = {
            "checks": [
                {
                    "id": "teaching_alignment_1",
                    "category": "teaching_alignment",
                    "section_id": "",
                    "passed": True,
                    "severity": "major",
                }
            ]
        }
        new_verification = {
            "is_refusal": False,
            "hallucination_risk": "none",
            "issues": [],
            "checks": [
                {
                    "id": "content_accuracy_1",
                    "category": "content_accuracy",
                    "section_id": "mc_2",
                    "passed": True,
                    "severity": "critical",
                }
            ],
        }
        merged_checks = merge_targeted_qc_checks(
            prior,
            new_verification,
            reverify_section_ids=["mc_2"],
        )
        ta_checks = [
            c for c in merged_checks if c.get("category") == "teaching_alignment"
        ]
        assert ta_checks == []

    def test_teaching_alignment_score_from_fresh_targeted_check(self):
        prior = {
            "checks": [
                {
                    "id": "teaching_alignment_1",
                    "category": "teaching_alignment",
                    "section_id": "",
                    "passed": False,
                    "severity": "major",
                }
            ]
        }
        new_verification = {
            "is_refusal": False,
            "hallucination_risk": "none",
            "issues": [],
            "checks": [
                {
                    "id": "teaching_alignment_retry",
                    "category": "teaching_alignment",
                    "section_id": "",
                    "passed": True,
                    "severity": "major",
                }
            ],
        }
        merged_checks = merge_targeted_qc_checks(
            prior,
            new_verification,
            reverify_section_ids=["mc_2"],
        )
        result = build_final_qc_result(
            {**new_verification, "checks": merged_checks},
            [],
            document=_SAMPLE_DOC,
            checklist=[],
            model="llama-3.3-70b-versatile",
        )
        assert result["scores"]["teaching_alignment"] == 10


class TestExtractPriorTeachingAlignment:
    def test_extracts_failed_document_level_check(self):
        from src.api.control.study_agent.prompts.qc.qc_retry_verification_prompt import (
            extract_prior_teaching_alignment_failure,
        )

        prior = {
            "checks": [
                {
                    "id": "ta_pass",
                    "category": "teaching_alignment",
                    "passed": True,
                },
                {
                    "id": "ta_fail",
                    "category": "teaching_alignment",
                    "section_id": "",
                    "passed": False,
                    "evidence": "Too thin.",
                },
            ]
        }
        result = extract_prior_teaching_alignment_failure(prior)
        assert result is not None
        assert result["id"] == "ta_fail"

    def test_ignores_section_scoped_failure(self):
        from src.api.control.study_agent.prompts.qc.qc_retry_verification_prompt import (
            extract_prior_teaching_alignment_failure,
        )

        prior = {
            "checks": [
                {
                    "id": "ta_section",
                    "category": "teaching_alignment",
                    "section_id": "ts_3",
                    "passed": False,
                }
            ]
        }
        assert extract_prior_teaching_alignment_failure(prior) is None

    def test_keeps_last_document_level_teaching_alignment(self):
        checks = [
            {
                "id": "ta_old",
                "category": "teaching_alignment",
                "section_id": "",
                "passed": False,
            },
            {
                "id": "ta_new",
                "category": "teaching_alignment",
                "section_id": "",
                "passed": True,
            },
        ]
        deduped = dedup_document_level_checks(checks)
        assert len(deduped) == 1
        assert deduped[0]["id"] == "ta_new"

    def test_section_scoped_checks_are_not_deduped(self):
        checks = [
            {
                "id": "ta_1",
                "category": "teaching_alignment",
                "section_id": "mc_1",
                "passed": False,
            },
            {
                "id": "ta_2",
                "category": "teaching_alignment",
                "section_id": "mc_2",
                "passed": True,
            },
        ]
        assert dedup_document_level_checks(checks) == checks


class TestNormalizeMustCoverSectionIds:
    def test_fills_empty_section_id(self):
        checks = [
            {"category": "must_cover", "checklist_id": "mc_4", "section_id": ""},
        ]
        checklist = [{"id": "mc_4", "section_id": "ts_2"}]
        result = normalize_must_cover_section_ids(checks, checklist)
        assert result[0]["section_id"] == "ts_2"

    def test_corrects_wrong_section_id(self):
        checks = [
            {"category": "must_cover", "checklist_id": "mc_2", "section_id": "ts_3"},
        ]
        checklist = [{"id": "mc_2", "section_id": "ts_2"}]
        result = normalize_must_cover_section_ids(checks, checklist)
        assert result[0]["section_id"] == "ts_2"

    def test_skips_non_must_cover(self):
        checks = [
            {"category": "content_accuracy", "section_id": "", "checklist_id": ""},
        ]
        checklist = [{"id": "mc_1", "section_id": "ts_1"}]
        result = normalize_must_cover_section_ids(checks, checklist)
        assert result[0]["section_id"] == ""


class TestTargetedCheckMerge:
    def test_replaces_checks_for_reverified_sections_only(self):
        """content_accuracy for a revised section is replaced; unrelated must_cover is kept."""
        prior = {
            "checks": [
                {
                    "id": "mc_1",
                    "category": "must_cover",
                    "checklist_id": "mc_1",
                    "section_id": "mc_1",
                    "passed": True,
                    "severity": "critical",
                },
                {
                    "id": "content_accuracy_1",
                    "category": "content_accuracy",
                    "section_id": "mc_2",
                    "passed": False,
                    "severity": "critical",
                },
            ]
        }
        new_verification = {
            "checks": [
                {
                    "id": "content_accuracy_1",
                    "category": "content_accuracy",
                    "section_id": "mc_2",
                    "passed": True,
                    "severity": "critical",
                }
            ]
        }
        merged = merge_targeted_qc_checks(
            prior,
            new_verification,
            reverify_section_ids=["mc_2"],
        )
        assert len(merged) == 2
        assert merged[0]["checklist_id"] == "mc_1"
        assert merged[1]["section_id"] == "mc_2"
        assert merged[1]["passed"] is True

    def test_teaching_alignment_no_section_id_evicted_on_revision(self):
        """Document-level teaching_alignment is evicted when any section is revised."""
        prior = {
            "checks": [
                {
                    "id": "teaching_alignment_1",
                    "category": "teaching_alignment",
                    "section_id": "",
                    "passed": False,
                    "severity": "major",
                    "evidence": "Derivation lacks clarity.",
                }
            ]
        }
        merged = merge_targeted_qc_checks(
            prior,
            {"checks": []},
            reverify_section_ids=["mc_5"],
        )
        assert merged == []

    def test_teaching_alignment_no_section_id_kept_without_revision(self):
        """Document-level teaching_alignment survives when no section is in reverify scope."""
        prior = {
            "checks": [
                {
                    "id": "teaching_alignment_1",
                    "category": "teaching_alignment",
                    "section_id": "",
                    "passed": True,
                    "severity": "major",
                }
            ]
        }
        merged = merge_targeted_qc_checks(
            prior,
            {"checks": []},
            reverify_section_ids=[],
        )
        assert len(merged) == 1
        assert merged[0]["category"] == "teaching_alignment"
        assert merged[0]["passed"] is True

    def test_teaching_alignment_with_section_id_only_evicted_when_in_scope(self):
        prior = {
            "checks": [
                {
                    "id": "ta_1",
                    "category": "teaching_alignment",
                    "section_id": "mc_3",
                    "passed": False,
                    "severity": "major",
                }
            ]
        }
        # Revising mc_5 — mc_3 check should survive
        merged_not_evicted = merge_targeted_qc_checks(
            prior, {"checks": []}, reverify_section_ids=["mc_5"]
        )
        assert len(merged_not_evicted) == 1

        # Revising mc_3 — check should be evicted
        merged_evicted = merge_targeted_qc_checks(
            prior, {"checks": []}, reverify_section_ids=["mc_3"]
        )
        assert merged_evicted == []

    def test_document_coherence_no_section_id_evicted_on_any_revision(self):
        """Document-wide document_coherence (no section_id) must be evicted when any section is revised."""
        prior = {
            "checks": [
                {
                    "id": "check_4",
                    "category": "document_coherence",
                    "section_id": "",
                    "passed": False,
                    "severity": "critical",
                }
            ]
        }
        merged = merge_targeted_qc_checks(
            prior,
            {"checks": []},
            reverify_section_ids=["mc_4"],
        )
        assert merged == [], "stale document-wide document_coherence must be evicted"

    def test_document_coherence_with_section_id_evicted_when_in_scope(self):
        prior = {
            "checks": [
                {
                    "id": "dc_mc4",
                    "category": "document_coherence",
                    "section_id": "mc_4",
                    "passed": False,
                    "severity": "critical",
                }
            ]
        }
        merged = merge_targeted_qc_checks(
            prior, {"checks": []}, reverify_section_ids=["mc_4"]
        )
        assert merged == []

    def test_dedup_new_check_wins_over_stale_kept_check(self):
        """If a stale check survives eviction but the new pass re-emits the same key, the new result wins."""
        prior = {
            "checks": [
                {
                    "id": "old_dc",
                    "category": "document_coherence",
                    "section_id": "mc_4",
                    "passed": False,
                    "severity": "critical",
                }
            ]
        }
        new_verification = {
            "checks": [
                {
                    "id": "new_dc",
                    "category": "document_coherence",
                    "section_id": "mc_4",
                    "passed": True,
                    "severity": "critical",
                }
            ]
        }
        # mc_4 is in scope so old_dc is evicted; new_dc is appended — only 1 entry
        merged = merge_targeted_qc_checks(
            prior,
            new_verification,
            reverify_section_ids=["mc_4"],
        )
        assert len(merged) == 1
        assert merged[0]["passed"] is True

    def test_check_targets_reverify_must_cover_by_checklist_id(self):
        assert check_targets_reverify(
            {
                "category": "must_cover",
                "checklist_id": "mc_5",
                "passed": False,
            },
            reverify_section_ids={"mc_2"},
            reverify_checklist_ids={"mc_5"},
        )

    def test_benzene_stale_mc4_evicted_via_canonical_section(self):
        """Benzene attempt 3: stale mc_4 (empty section_id) evicted when ts_2 is re-verified."""
        checklist = [
            {
                "id": "mc_4",
                "section_id": "ts_2",
                "concept": "Substituents",
                "priority": "required",
            }
        ]
        prior = {
            "checks": [
                {
                    "id": "mc_4",
                    "category": "must_cover",
                    "checklist_id": "mc_4",
                    "section_id": "",
                    "passed": False,
                    "severity": "major",
                }
            ]
        }
        new_verification = {
            "checks": [
                {
                    "id": "retry_1",
                    "category": "content_accuracy",
                    "section_id": "ts_2",
                    "passed": True,
                    "severity": "critical",
                }
            ]
        }
        merged = merge_targeted_qc_checks(
            prior,
            new_verification,
            reverify_section_ids=["ts_2"],
            checklist=checklist,
        )
        failing_mc4 = [
            c
            for c in merged
            if c.get("category") == "must_cover"
            and c.get("checklist_id") == "mc_4"
            and not c.get("passed")
        ]
        assert failing_mc4 == []

    def test_calculus_duplicate_mc2_deduped_to_pass(self):
        """Calculus attempt 3: duplicate mc_2 rows collapse to the fresh pass at ts_2."""
        checklist = [
            {
                "id": "mc_2",
                "section_id": "ts_2",
                "concept": "Limits",
                "priority": "required",
            }
        ]
        prior = {
            "checks": [
                {
                    "id": "mc_2",
                    "category": "must_cover",
                    "checklist_id": "mc_2",
                    "section_id": "ts_3",
                    "passed": False,
                    "severity": "critical",
                }
            ]
        }
        new_verification = {
            "checks": [
                {
                    "id": "mc_2",
                    "category": "must_cover",
                    "checklist_id": "mc_2",
                    "section_id": "ts_2",
                    "passed": True,
                    "severity": "critical",
                }
            ]
        }
        merged = merge_targeted_qc_checks(
            prior,
            new_verification,
            reverify_section_ids=["ts_2"],
            checklist=checklist,
        )
        mc2_rows = [c for c in merged if c.get("checklist_id") == "mc_2"]
        assert len(mc2_rows) == 1
        assert mc2_rows[0]["passed"] is True
        assert mc2_rows[0]["section_id"] == "ts_2"

    def test_must_cover_evicted_by_canonical_section_without_checklist_in_ids(self):
        checklist = [{"id": "mc_4", "section_id": "ts_2"}]
        assert check_targets_reverify(
            {
                "category": "must_cover",
                "checklist_id": "mc_4",
                "section_id": "",
                "passed": False,
            },
            reverify_section_ids={"ts_2"},
            reverify_checklist_ids=set(),
            checklist=checklist,
        )


class TestArtifactReproduction:
    """End-to-end regression for 2026-06-25 Benzene/Calculus merge failures."""

    def test_benzene_stale_mc4_no_longer_blocks_delivery(self):
        """After merge evicts stale mc_4, no critical failures remain and result is deliverable."""
        checklist = [
            {
                "id": "mc_4",
                "section_id": "ts_2",
                "concept": "Substituents",
                "priority": "required",
            }
        ]
        prior = {
            "checks": [
                {
                    "id": "mc_1",
                    "category": "must_cover",
                    "checklist_id": "mc_1",
                    "section_id": "ts_1",
                    "passed": True,
                    "severity": "critical",
                },
                {
                    "id": "mc_4",
                    "category": "must_cover",
                    "checklist_id": "mc_4",
                    "section_id": "",
                    "passed": False,
                    "severity": "major",
                },
            ]
        }
        new_verification = {
            "checks": [
                {
                    "id": "retry_1",
                    "category": "content_accuracy",
                    "section_id": "ts_2",
                    "passed": True,
                    "severity": "critical",
                }
            ]
        }
        merged = merge_targeted_qc_checks(
            prior,
            new_verification,
            reverify_section_ids=["ts_2"],
            checklist=checklist,
        )
        failing_mc4 = [
            c
            for c in merged
            if c.get("category") == "must_cover"
            and c.get("checklist_id") == "mc_4"
            and not c.get("passed")
        ]
        assert failing_mc4 == []

        overall = derive_overall_status(merged, "none", False)
        failed = extract_failed_checks(merged)
        assert is_qc_deliverable(
            overall_status=overall,
            failed_checks=failed,
            hallucination_risk="none",
            is_refusal=False,
        )

    def test_calculus_merge_single_passing_mc2_enables_pass(self):
        """After merge, critical mc_2 failure is replaced by the fresh pass."""
        checklist = [
            {
                "id": "mc_2",
                "section_id": "ts_2",
                "concept": "Derivative",
                "priority": "required",
            }
        ]
        prior = {
            "checks": [
                {
                    "id": "mc_1",
                    "category": "must_cover",
                    "checklist_id": "mc_1",
                    "section_id": "ts_1",
                    "passed": True,
                    "severity": "critical",
                },
                {
                    "id": "mc_2",
                    "category": "must_cover",
                    "checklist_id": "mc_2",
                    "section_id": "ts_3",
                    "passed": False,
                    "severity": "critical",
                },
            ]
        }
        new_verification = {
            "checks": [
                {
                    "id": "mc_2",
                    "category": "must_cover",
                    "checklist_id": "mc_2",
                    "section_id": "ts_2",
                    "passed": True,
                    "severity": "critical",
                }
            ]
        }
        merged = merge_targeted_qc_checks(
            prior,
            new_verification,
            reverify_section_ids=["ts_2"],
            checklist=checklist,
        )
        mc2_rows = [c for c in merged if c.get("checklist_id") == "mc_2"]
        assert len(mc2_rows) == 1
        assert mc2_rows[0]["passed"] is True

        overall = derive_overall_status(merged, "none", False)
        failed = extract_failed_checks(merged)
        assert overall == "pass"
        assert is_qc_deliverable(
            overall_status=overall,
            failed_checks=failed,
            hallucination_risk="none",
            is_refusal=False,
        )
