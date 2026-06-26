# tests/test_concept_checklist_prompt.py
"""Smoke tests for concept checklist prompt guardrails."""

from __future__ import annotations

from src.api.control.study_agent.prompts.concept import concept_checklist_prompt


def test_system_prompt_includes_domain_disambiguation_for_software_topics() -> None:
    system = concept_checklist_prompt.SYSTEM_PROMPT
    assert "concurrency" in system.lower()
    assert "Programming" in system
    assert "operating-system concurrency" in system.lower() or "async" in system.lower()


def test_system_prompt_bans_diagrams_and_tables_in_requirement_and_depth_gate() -> None:
    system = concept_checklist_prompt.SYSTEM_PROMPT
    assert "FORMAT BAN" in system
    assert "requirement AND depth_gate" in system
    assert "diagrams" in system.lower()
    assert "tables" in system.lower()


def test_system_prompt_has_programming_good_bad_examples() -> None:
    system = concept_checklist_prompt.SYSTEM_PROMPT
    assert "Programming GOOD" in system
    assert "Derive the useState hook from the React source code" in system


def test_system_prompt_domain_aligned_depth_gate_rule() -> None:
    system = concept_checklist_prompt.SYSTEM_PROMPT
    assert "DOMAIN-ALIGNED depth_gate" in system
    assert "Never put STEM derivation language" in system


def test_system_prompt_appropriate_verbs_rule_is_uniform() -> None:
    system = concept_checklist_prompt.SYSTEM_PROMPT
    assert "APPROPRIATE VERBS" in system
    assert "applies uniformly to all domains" in system


def test_system_prompt_minimum_coverage_rules() -> None:
    system = concept_checklist_prompt.SYSTEM_PROMPT
    assert "MINIMUM COVERAGE" in system
    assert "Never return fewer than 4 checklist items" in system
    assert "SECTION LINKAGE" in system


def test_system_prompt_depth_gate_requires_multiple_components() -> None:
    system = concept_checklist_prompt.SYSTEM_PROMPT
    assert "2–4 specific, independently checkable evidence components" in system


def test_user_message_is_concise() -> None:
    msg = concept_checklist_prompt.build_user_message("Concurrency")
    assert "Generate the JSON plan now." in msg
    assert "multi-part depth_gates" in msg
    assert "coverage-complete" not in msg


def test_user_message_includes_teaching_instruction() -> None:
    msg = concept_checklist_prompt.build_user_message(
        "Hooks",
        teaching_instruction="Explain useState clearly.",
    )
    assert "<teaching_instruction>" in msg
    assert "useState" in msg
