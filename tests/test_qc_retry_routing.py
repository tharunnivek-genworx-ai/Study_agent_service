# tests/test_qc_retry_routing.py
"""Unit tests for qc_retry_routing."""

from __future__ import annotations

from unittest.mock import patch

from src.api.utils.study_agent_utils.quality_check_utils.results.retry_routing import (
    _coerce_llm_recommendation_mode,
    _reconcile_mode,
    classify_retry_routing,
)


def _doc(*sections: dict) -> dict:
    return {"sections": list(sections)}


def _check(
    *,
    id: str = "c1",
    category: str = "content_accuracy",
    passed: bool = False,
    severity: str = "critical",
    section_id: str | None = None,
    checklist_id: str | None = None,
    evidence: str = "bad claim",
    corrective_hint: str = "fix it",
) -> dict:
    check: dict = {
        "id": id,
        "category": category,
        "passed": passed,
        "severity": severity,
        "evidence": evidence,
        "corrective_hint": corrective_hint,
    }
    if section_id is not None:
        check["section_id"] = section_id
    if checklist_id is not None:
        check["checklist_id"] = checklist_id
    return check


_CHECKLIST = [
    {
        "id": "mc_1",
        "concept": "Intro",
        "requirement": "Cover intro",
        "priority": "required",
    },
    {
        "id": "mc_2",
        "concept": "Basics",
        "requirement": "Cover basics",
        "priority": "required",
    },
    {
        "id": "mc_3",
        "concept": "Examples",
        "requirement": "Cover examples",
        "priority": "required",
    },
    {
        "id": "mc_4",
        "concept": "Advanced",
        "requirement": "Cover advanced",
        "priority": "required",
    },
    {
        "id": "mc_5",
        "concept": "Pitfalls",
        "requirement": "Cover pitfalls",
        "priority": "required",
    },
]


class TestClassifyRetryRouting:
    def test_no_failures_returns_none(self):
        qc_result = {"checks": [_check(passed=True)], "failed_checks": []}
        result = classify_retry_routing(qc_result, _doc(), _CHECKLIST)
        assert result.mode == "none"
        assert result.failed_section_ids == []
        assert result.missing_checklist_ids == []

    def test_isolated_section_failure_uses_section_patch(self):
        document = _doc(
            {"id": "mc_1", "heading": "Intro", "content": "intro"},
            {"id": "mc_2", "heading": "Basics", "content": "basics"},
        )
        qc_result = {
            "checks": [
                _check(
                    id="content_accuracy_1",
                    category="content_accuracy",
                    section_id="mc_2",
                )
            ]
        }
        result = classify_retry_routing(qc_result, document, _CHECKLIST)
        assert result.mode == "section_patch"
        assert result.failed_section_ids == ["mc_2"]
        assert result.missing_checklist_ids == []
        assert result.section_failures[0]["section_id"] == "mc_2"
        assert result.section_failures[0]["heading"] == "Basics"
        assert len(result.section_failures[0]["failures"]) == 1

    def test_missing_checklist_section_uses_section_insert(self):
        document = _doc({"id": "mc_1", "heading": "Intro", "content": "intro"})
        qc_result = {
            "checks": [
                _check(
                    id="mc_5",
                    category="must_cover",
                    checklist_id="mc_5",
                    severity="critical",
                )
            ]
        }
        result = classify_retry_routing(qc_result, document, _CHECKLIST)
        assert result.mode == "section_insert"
        assert result.failed_section_ids == []
        assert result.missing_checklist_ids == ["mc_5"]

    def test_failed_section_and_missing_item_use_patch_then_insert(self):
        checklist = _CHECKLIST + [
            {
                "id": "mc_6",
                "concept": "Summary",
                "requirement": "Cover summary",
                "priority": "required",
            }
        ]
        document = _doc(
            {"id": "mc_1", "heading": "Intro", "content": "intro"},
            {"id": "mc_2", "heading": "Basics", "content": "basics"},
        )
        qc_result = {
            "checks": [
                _check(
                    id="content_accuracy_1",
                    category="content_accuracy",
                    section_id="mc_2",
                ),
                _check(
                    id="mc_6",
                    category="must_cover",
                    checklist_id="mc_6",
                    severity="critical",
                ),
            ]
        }
        result = classify_retry_routing(qc_result, document, checklist)
        assert result.mode == "section_patch_then_insert"
        assert result.failed_section_ids == ["mc_2"]
        assert "mc_6" in result.missing_checklist_ids

    def test_must_cover_failure_in_existing_section_maps_to_patch(self):
        document = _doc({"id": "mc_2", "heading": "Basics", "content": "thin"})
        qc_result = {
            "checks": [
                _check(
                    id="mc_2",
                    category="must_cover",
                    checklist_id="mc_2",
                    severity="critical",
                    evidence="Requirement not met",
                )
            ]
        }
        result = classify_retry_routing(qc_result, document, _CHECKLIST)
        assert result.mode == "section_patch"
        assert result.failed_section_ids == ["mc_2"]

    def test_must_cover_maps_checklist_item_to_section_id(self):
        checklist = [
            {
                "id": "mc_1",
                "section_id": "ts_1",
                "concept": "Intro",
                "requirement": "Cover intro",
                "priority": "required",
            },
            {
                "id": "mc_2",
                "section_id": "ts_2",
                "concept": "Basics",
                "requirement": "Cover basics",
                "priority": "required",
            },
            {
                "id": "mc_3",
                "section_id": "ts_3",
                "concept": "Examples",
                "requirement": "Cover examples",
                "priority": "required",
            },
            {
                "id": "mc_4",
                "section_id": "ts_4",
                "concept": "Advanced",
                "requirement": "Cover advanced",
                "priority": "required",
            },
            {
                "id": "mc_5",
                "section_id": "ts_5",
                "concept": "Pitfalls",
                "requirement": "Cover pitfalls",
                "priority": "required",
            },
        ]
        document = _doc(
            {"id": "ts_1", "heading": "Intro", "content": "intro"},
            {"id": "ts_2", "heading": "Basics", "content": "basics"},
            {"id": "ts_3", "heading": "Examples", "content": "thin"},
            {"id": "ts_4", "heading": "Advanced", "content": "advanced"},
            {"id": "ts_5", "heading": "Pitfalls", "content": "pitfalls"},
        )
        qc_result = {
            "checks": [
                _check(
                    id="mc_3",
                    category="must_cover",
                    checklist_id="mc_3",
                    severity="critical",
                )
            ]
        }
        result = classify_retry_routing(qc_result, document, checklist)
        assert result.mode == "section_patch"
        assert result.failed_section_ids == ["ts_3"]

    def test_teaching_alignment_critical_triggers_full_regeneration(self):
        document = _doc({"id": "mc_1", "heading": "Intro", "content": "intro"})
        qc_result = {
            "checks": [
                _check(
                    id="teaching_alignment",
                    category="teaching_alignment",
                    severity="critical",
                )
            ]
        }
        result = classify_retry_routing(qc_result, document, _CHECKLIST)
        assert result.mode == "full_regeneration"
        assert "teaching_alignment" in result.rationale

    def test_many_failed_sections_trigger_full_regeneration(self):
        document = _doc(
            {"id": "mc_1", "heading": "One", "content": "one"},
            {"id": "mc_2", "heading": "Two", "content": "two"},
            {"id": "mc_3", "heading": "Three", "content": "three"},
            {"id": "mc_4", "heading": "Four", "content": "four"},
        )
        qc_result = {
            "checks": [
                _check(id="c1", category="content_accuracy", section_id="mc_1"),
                _check(id="c2", category="content_accuracy", section_id="mc_2"),
                _check(id="c3", category="code_quality", section_id="mc_3"),
                _check(id="c4", category="stack_fidelity", section_id="mc_4"),
            ]
        }
        result = classify_retry_routing(qc_result, document, _CHECKLIST)
        assert result.mode == "full_regeneration"
        assert (
            "4 distinct failed section ids" in result.rationale
            or "required checklist sections missing or failed" in result.rationale
        )

    def test_coverage_threshold_triggers_full_regeneration(self):
        document = _doc(
            {"id": "mc_1", "heading": "Intro", "content": "intro"},
            {"id": "mc_2", "heading": "Basics", "content": "basics"},
        )
        qc_result = {
            "checks": [
                _check(
                    id="mc_3",
                    category="must_cover",
                    checklist_id="mc_3",
                    severity="critical",
                ),
                _check(
                    id="mc_4",
                    category="must_cover",
                    checklist_id="mc_4",
                    severity="critical",
                ),
            ]
        }
        result = classify_retry_routing(qc_result, document, _CHECKLIST)
        assert result.mode == "full_regeneration"
        assert "required checklist sections missing or failed" in result.rationale

    def test_topic_split_section_failures_trigger_full_regen_via_coverage_rule(self):
        """ts_* failures must map to mc_* for the 40% required-coverage rule."""
        checklist = [
            {
                "id": "mc_1",
                "section_id": "ts_1",
                "concept": "Limits",
                "requirement": "Cover limits",
                "priority": "required",
            },
            {
                "id": "mc_2",
                "section_id": "ts_2",
                "concept": "Derivatives",
                "requirement": "Cover derivatives",
                "priority": "required",
            },
            {
                "id": "mc_3",
                "section_id": "ts_3",
                "concept": "Power rule",
                "requirement": "Derive power rule",
                "priority": "required",
            },
            {
                "id": "mc_4",
                "section_id": "ts_4",
                "concept": "Integrals",
                "requirement": "Cover integrals",
                "priority": "required",
            },
            {
                "id": "mc_5",
                "section_id": "ts_5",
                "concept": "Optimization",
                "requirement": "Cover optimization",
                "priority": "required",
            },
            {
                "id": "mc_6",
                "section_id": "ts_6",
                "concept": "Diff eq",
                "requirement": "Cover differential equations",
                "priority": "required",
            },
        ]
        topic_split = [
            {"id": f"ts_{i}", "heading": f"Section {i}"} for i in range(1, 7)
        ]
        document = _doc(
            *[
                {"id": f"ts_{i}", "heading": f"Section {i}", "content": "content"}
                for i in range(1, 7)
            ]
        )
        qc_result = {
            "checks": [
                _check(
                    id="mc_1",
                    category="must_cover",
                    checklist_id="mc_1",
                    passed=True,
                    section_id="ts_1",
                ),
                _check(
                    id="mc_2",
                    category="must_cover",
                    checklist_id="mc_2",
                    passed=True,
                    section_id="ts_2",
                ),
                _check(
                    id="mc_3",
                    category="must_cover",
                    checklist_id="mc_3",
                    passed=True,
                    section_id="ts_3",
                ),
                _check(
                    id="det_equation_in_content",
                    category="document_coherence",
                    section_id="ts_1",
                    evidence="Prose contains display-math patterns",
                ),
                _check(
                    id="det_equation_in_content",
                    category="document_coherence",
                    section_id="ts_2",
                    evidence="Prose contains display-math patterns",
                ),
                _check(
                    id="det_equation_in_content",
                    category="document_coherence",
                    section_id="ts_3",
                    evidence="Prose contains display-math patterns",
                ),
            ]
        }
        result = classify_retry_routing(
            qc_result, document, checklist, topic_split=topic_split
        )
        assert result.mode == "full_regeneration"
        assert "required checklist sections missing or failed" in result.rationale
        assert result.failed_section_ids == ["ts_1", "ts_2", "ts_3"]

    def test_topic_split_two_section_failures_stay_section_patch(self):
        """Under 40% of required items affected → section_patch, not full regen."""
        checklist = [
            {
                "id": "mc_1",
                "section_id": "ts_1",
                "concept": "Intro",
                "requirement": "Cover intro",
                "priority": "required",
            },
            {
                "id": "mc_2",
                "section_id": "ts_2",
                "concept": "Basics",
                "requirement": "Cover basics",
                "priority": "required",
            },
            {
                "id": "mc_3",
                "section_id": "ts_3",
                "concept": "Examples",
                "requirement": "Cover examples",
                "priority": "required",
            },
            {
                "id": "mc_4",
                "section_id": "ts_4",
                "concept": "Advanced",
                "requirement": "Cover advanced",
                "priority": "required",
            },
            {
                "id": "mc_5",
                "section_id": "ts_5",
                "concept": "Pitfalls",
                "requirement": "Cover pitfalls",
                "priority": "required",
            },
            {
                "id": "mc_6",
                "section_id": "ts_6",
                "concept": "Summary",
                "requirement": "Cover summary",
                "priority": "required",
            },
        ]
        document = _doc(
            {"id": "ts_1", "heading": "Intro", "content": "intro"},
            {"id": "ts_2", "heading": "Basics", "content": "basics"},
            {"id": "ts_3", "heading": "Examples", "content": "examples"},
            {"id": "ts_4", "heading": "Advanced", "content": "advanced"},
            {"id": "ts_5", "heading": "Pitfalls", "content": "pitfalls"},
            {"id": "ts_6", "heading": "Summary", "content": "summary"},
        )
        qc_result = {
            "checks": [
                _check(
                    id="det_equation_in_content",
                    category="document_coherence",
                    section_id="ts_1",
                ),
                _check(
                    id="det_equation_in_content",
                    category="document_coherence",
                    section_id="ts_2",
                ),
            ]
        }
        result = classify_retry_routing(qc_result, document, checklist)
        assert result.mode == "section_patch"
        assert result.failed_section_ids == ["ts_1", "ts_2"]

    def test_structure_coverage_widespread_triggers_full_regeneration(self):
        document = _doc({"id": "mc_1", "heading": "Intro", "content": "intro"})
        qc_result = {
            "checks": [
                {
                    "id": "det_structure_coverage",
                    "category": "structure",
                    "passed": False,
                    "severity": "critical",
                    "evidence": "Missing section ids: mc_2, mc_3, mc_4, mc_5",
                }
            ]
        }
        result = classify_retry_routing(qc_result, document, _CHECKLIST)
        assert result.mode == "full_regeneration"
        assert "det_structure_coverage" in result.rationale

    def test_structure_coverage_reuses_precomputed_missing_ids(self):
        """Passing structure_missing_ids avoids redundant coverage validation."""
        document = _doc({"id": "mc_1", "heading": "Intro", "content": "intro"})
        qc_result = {
            "checks": [
                {
                    "id": "det_structure_coverage",
                    "category": "structure",
                    "passed": False,
                    "severity": "critical",
                    "evidence": "Missing section ids: mc_2, mc_3, mc_4, mc_5",
                }
            ]
        }
        precomputed = {"mc_2", "mc_3", "mc_4", "mc_5"}
        with patch(
            "src.api.utils.study_agent_utils.quality_check_utils.results.retry_routing.validate_section_id_coverage"
        ) as mock_validate:
            result = classify_retry_routing(
                qc_result,
                document,
                _CHECKLIST,
                structure_missing_ids=precomputed,
            )
        mock_validate.assert_not_called()
        assert result.mode == "full_regeneration"
        assert (
            "mc_6" in result.missing_checklist_ids
            or "mc_2" in result.missing_checklist_ids
        )

    def test_isolated_structure_missing_section_uses_section_insert(self):
        checklist = [
            {
                "id": "mc_6",
                "section_id": "ts_7",
                "concept": "Pitfalls",
                "requirement": "Cover pitfalls",
                "priority": "required",
            },
        ]
        topic_split = [
            {"id": "ts_1", "heading": "Intro"},
            {"id": "ts_2", "heading": "Classes"},
            {"id": "ts_3", "heading": "Inheritance"},
            {"id": "ts_4", "heading": "Polymorphism"},
            {"id": "ts_5", "heading": "Encapsulation"},
            {"id": "ts_6", "heading": "Abstraction"},
            {"id": "ts_7", "heading": "Pitfalls"},
        ]
        document = _doc(
            {"id": "ts_1", "heading": "Intro", "content": "intro"},
            {"id": "ts_2", "heading": "Classes", "content": "classes"},
            {"id": "ts_3", "heading": "Inheritance", "content": "inheritance"},
            {"id": "ts_4", "heading": "Polymorphism", "content": "polymorphism"},
            {"id": "ts_5", "heading": "Encapsulation", "content": "encapsulation"},
            {"id": "ts_6", "heading": "Abstraction", "content": "abstraction"},
        )
        qc_result = {
            "checks": [
                {
                    "id": "det_structure_coverage",
                    "category": "structure",
                    "passed": False,
                    "severity": "critical",
                    "evidence": "Missing section ids: ts_7",
                },
                _check(
                    id="mc_1",
                    category="must_cover",
                    checklist_id="mc_1",
                    passed=True,
                    severity="critical",
                ),
            ],
            "retry_recommendation": {
                "mode": "none",
                "failed_section_ids": [],
                "missing_checklist_ids": [],
                "rationale": "All checks passed",
            },
        }
        result = classify_retry_routing(
            qc_result, document, checklist, topic_split=topic_split
        )
        assert result.mode == "section_insert"
        assert result.missing_checklist_ids == ["mc_6"]
        assert "section_insert" in result.rationale

    def test_honors_compatible_llm_recommendation(self):
        document = _doc(
            {"id": "mc_1", "heading": "Intro", "content": "intro"},
            {"id": "mc_2", "heading": "Basics", "content": "basics"},
        )
        qc_result = {
            "checks": [
                _check(
                    id="content_accuracy_1",
                    category="content_accuracy",
                    section_id="mc_2",
                )
            ],
            "retry_recommendation": {
                "mode": "section_patch",
                "failed_section_ids": ["mc_2"],
                "missing_checklist_ids": [],
                "rationale": "Only mc_2 needs a rewrite",
            },
        }
        result = classify_retry_routing(qc_result, document, _CHECKLIST)
        assert result.mode == "section_patch"
        assert result.rationale == "Only mc_2 needs a rewrite"

    def test_overrides_llm_patch_when_full_regen_is_safer(self):
        document = _doc(
            {"id": "mc_1", "heading": "One", "content": "one"},
            {"id": "mc_2", "heading": "Two", "content": "two"},
            {"id": "mc_3", "heading": "Three", "content": "three"},
            {"id": "mc_4", "heading": "Four", "content": "four"},
        )
        qc_result = {
            "checks": [
                _check(id="c1", category="content_accuracy", section_id="mc_1"),
                _check(id="c2", category="content_accuracy", section_id="mc_2"),
                _check(id="c3", category="code_quality", section_id="mc_3"),
                _check(id="c4", category="stack_fidelity", section_id="mc_4"),
            ],
            "retry_recommendation": {
                "mode": "section_patch",
                "failed_section_ids": ["mc_1", "mc_2", "mc_3", "mc_4"],
                "missing_checklist_ids": [],
                "rationale": "Patch each section individually",
            },
        }
        result = classify_retry_routing(qc_result, document, _CHECKLIST)
        assert result.mode == "full_regeneration"

    def test_llm_full_regeneration_does_not_override_scoped_deterministic_mode(self):
        document = _doc(
            {"id": "mc_1", "heading": "Intro", "content": "intro"},
            {"id": "mc_2", "heading": "Basics", "content": "basics"},
        )
        qc_result = {
            "checks": [
                _check(
                    id="content_accuracy_1",
                    category="content_accuracy",
                    section_id="mc_2",
                )
            ],
            "retry_recommendation": {
                "mode": "full_regeneration",
                "failed_section_ids": ["mc_2"],
                "missing_checklist_ids": [],
                "rationale": "Document needs a full rewrite",
            },
        }
        result = classify_retry_routing(qc_result, document, _CHECKLIST)
        assert result.mode == "section_patch"
        assert result.failed_section_ids == ["mc_2"]


class TestCoerceLlmRecommendationMode:
    def test_accepts_valid_modes(self):
        assert _coerce_llm_recommendation_mode("section_patch") == "section_patch"
        assert (
            _coerce_llm_recommendation_mode("full_regeneration") == "full_regeneration"
        )
        assert _coerce_llm_recommendation_mode("none") == "none"

    def test_rejects_unknown_mode(self):
        assert _coerce_llm_recommendation_mode("nemotron_rewrite") is None
        assert _coerce_llm_recommendation_mode("") is None
        assert _coerce_llm_recommendation_mode(None) is None


class TestReconcileMode:
    def test_force_full_regen_always_wins(self):
        assert (
            _reconcile_mode(
                deterministic="section_patch",
                llm_recommendation_mode="section_patch",
                force_full_regen=True,
                failed_section_ids={"mc_1"},
                missing_checklist_ids=set(),
                teaching_alignment_sole_failure=False,
            )
            == "full_regeneration"
        )

    def test_llm_full_regeneration_does_not_override_section_patch(self):
        assert (
            _reconcile_mode(
                deterministic="section_patch",
                llm_recommendation_mode="full_regeneration",
                force_full_regen=False,
                failed_section_ids={"mc_2"},
                missing_checklist_ids=set(),
                teaching_alignment_sole_failure=False,
            )
            == "section_patch"
        )

    def test_teaching_alignment_sole_failure_triggers_full_regen_when_deterministic_none(
        self,
    ):
        assert (
            _reconcile_mode(
                deterministic="none",
                llm_recommendation_mode=None,
                force_full_regen=False,
                failed_section_ids=set(),
                missing_checklist_ids=set(),
                teaching_alignment_sole_failure=True,
            )
            == "full_regeneration"
        )

    def test_compatible_llm_section_patch_honored(self):
        assert (
            _reconcile_mode(
                deterministic="section_patch",
                llm_recommendation_mode="section_patch",
                force_full_regen=False,
                failed_section_ids={"mc_2"},
                missing_checklist_ids=set(),
                teaching_alignment_sole_failure=False,
            )
            == "section_patch"
        )
