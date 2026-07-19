# tests/test_concept_checklist_prompt.py
"""Smoke tests for concept checklist prompt guardrails."""

from __future__ import annotations

from src.api.control.study_agent.prompts.concept import (
    build_concept_checklist_system_prompt,
    build_concept_checklist_user_message,
)
from src.api.control.study_agent.prompts.concept.shared_blocks import (
    STEM_NO_RUNNABLE_CODE_BLOCK,
)
from test_new_prompts.prompts import concept_checklist_prompt


def test_generation_prompt_includes_stem_no_runnable_code_block() -> None:
    system = build_concept_checklist_system_prompt("generate")
    assert STEM_NO_RUNNABLE_CODE_BLOCK in system
    assert "STEM DOMAIN LOCK" in system
    assert "Family B is forbidden" in system
    assert "keyed only to the domain label STEM" in system


def test_generation_prompt_includes_a1_viability_and_stem_app_routing() -> None:
    system = build_concept_checklist_system_prompt("generate")
    assert "A1 VIABILITY GATE" in system
    assert "STEM APPLICATION / ALGORITHM / EXPERIMENT ROUTING" in system
    assert "A2 HARD FILL RULE" in system
    assert "prefer FAMILY C" in system


def test_rework_prompt_includes_stem_no_runnable_code_block() -> None:
    system = build_concept_checklist_system_prompt("improve")
    assert STEM_NO_RUNNABLE_CODE_BLOCK in system
    assert "Family B count is exactly zero" in system
    assert "A1 VIABILITY GATE" in system


def test_user_message_closing_bans_stem_family_b() -> None:
    msg = build_concept_checklist_user_message("Quantum Mechanics")
    assert "If domain is STEM, Family B is forbidden" in msg
    assert "prefer Family C" in msg
    assert "A1 VIABILITY GATE" in msg


def test_system_prompt_includes_domain_disambiguation_for_software_topics() -> None:
    system = concept_checklist_prompt.SYSTEM_PROMPT
    assert "Programming" in system
    assert "syntax and runtime behaviour" in system.lower()


def test_system_prompt_bans_diagrams_and_tables_in_requirement_and_depth_gate() -> None:
    system = concept_checklist_prompt.SYSTEM_PROMPT
    assert "HARD WORD BAN" in system
    assert "Family A" in system
    assert "Family B" in system


def test_system_prompt_has_programming_good_bad_examples() -> None:
    system = concept_checklist_prompt.SYSTEM_PROMPT
    assert "Worked example" in system
    assert "debounce function in JavaScript" in system


def test_system_prompt_domain_aligned_depth_gate_rule() -> None:
    system = concept_checklist_prompt.SYSTEM_PROMPT
    assert "FAMILY A — MATHEMATICAL" in system
    assert "These words belong ONLY to Family A" in system


def test_system_prompt_appropriate_verbs_rule_is_uniform() -> None:
    system = concept_checklist_prompt.SYSTEM_PROMPT
    assert "requirement skeleton" in system
    assert (
        "Derive/Prove/Calculate/Show" in system
        or "Derive/Prove/Calculate/Show that" in system
    )
    assert "Implement/Build/Write/Debug" in system


def test_system_prompt_minimum_coverage_rules() -> None:
    system = concept_checklist_prompt.SYSTEM_PROMPT
    assert "4–8 sections" in system
    assert "4–10 items" in system
    assert "section_id" in system


def test_system_prompt_depth_gate_requires_multiple_components() -> None:
    system = concept_checklist_prompt.SYSTEM_PROMPT
    assert "depth_gate skeleton" in system
    assert "fill only the brackets" in system


def test_user_message_is_concise() -> None:
    msg = concept_checklist_prompt.build_user_message("Concurrency")
    assert "Generate the JSON plan now." in msg
    assert "fully filled-in depth_gates" in msg
    assert "coverage-complete" not in msg


def test_user_message_includes_teaching_instruction() -> None:
    msg = concept_checklist_prompt.build_user_message(
        "Hooks",
        teaching_instruction="Explain useState clearly.",
    )
    assert "<teaching_instruction>" in msg
    assert "useState" in msg
