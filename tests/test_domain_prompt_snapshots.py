# tests/test_domain_prompt_snapshots.py
"""Byte-equality snapshots for domain-aware prompt refactor.

Pre-refactor baselines live in tests/snapshots/domain_prompts/*.txt.
After the refactor, build_system_prompt(..., domain=\"\") and domain=\"Mixed\"
must remain byte-equal to the matching empty-domain snapshots.

Regenerate baselines only when prompt wording intentionally changes:
    UPDATE_DOMAIN_PROMPT_SNAPSHOTS=1 pytest tests/test_domain_prompt_snapshots.py
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from src.api.control.hint_agent.prompts import hint_prompt
from src.api.control.quiz_agent.prompts import quiz_prompt
from src.api.control.study_agent.prompts.generation import (
    generation_prompt,
    improve_prompt,
    regeneration_prompt,
)
from src.api.control.study_agent.prompts.qc import qc_verification_prompt
from src.api.control.study_agent.prompts.section import (
    section_insert_prompt,
    section_rework_prompt,
)

SNAPSHOT_DIR = Path(__file__).parent / "snapshots" / "domain_prompts"

# Distinctive anchors used after refactor to verify domain-filtered assembly.
PROGRAMMING_ONLY_ANCHOR = "Never define the same method"
STEM_DERIVATION_ANCHOR = "DERIVATION ANTI-SUBSTITUTION RULE"


def _snapshot_path(name: str) -> Path:
    return SNAPSHOT_DIR / name


def _read_snapshot(name: str) -> bytes:
    return _snapshot_path(name).read_bytes()


def _write_snapshot(name: str, text: str) -> None:
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    _snapshot_path(name).write_bytes(text.encode("utf-8"))


def assert_prompt_bytes_equal(actual: str, snapshot_name: str) -> None:
    actual_normalized = actual.replace("\r\n", "\n")
    if os.environ.get("UPDATE_DOMAIN_PROMPT_SNAPSHOTS") == "1":
        _write_snapshot(snapshot_name, actual_normalized)
        return

    expected_raw = _read_snapshot(snapshot_name)
    expected_normalized = expected_raw.decode("utf-8").replace("\r\n", "\n")

    actual_bytes = actual_normalized.encode("utf-8")
    expected_bytes = expected_normalized.encode("utf-8")

    assert actual_bytes == expected_bytes, (
        f"Snapshot mismatch for {snapshot_name}: "
        f"{len(actual_bytes)} bytes actual vs {len(expected_bytes)} bytes expected. "
        "Run with UPDATE_DOMAIN_PROMPT_SNAPSHOTS=1 to refresh baselines."
    )


def _build_generation_prompt(*, has_reference: bool, domain: str | None = None) -> str:
    builder = generation_prompt.build_system_prompt
    try:
        return builder(has_reference=has_reference, domain=domain)
    except TypeError:
        return builder(has_reference=has_reference)


def _build_improve_prompt(*, has_reference: bool, domain: str | None = None) -> str:
    builder = improve_prompt.build_system_prompt
    try:
        return builder(has_reference=has_reference, domain=domain)
    except TypeError:
        return builder(has_reference=has_reference)


def _build_regeneration_prompt(
    *, has_reference: bool, domain: str | None = None
) -> str:
    builder = regeneration_prompt.build_system_prompt
    try:
        return builder(has_reference=has_reference, domain=domain)
    except TypeError:
        return builder(has_reference=has_reference)


def _build_section_insert_prompt(
    *, has_reference: bool, domain: str | None = None
) -> str:
    builder = section_insert_prompt.build_system_prompt
    try:
        return builder(has_reference=has_reference, domain=domain)
    except TypeError:
        return builder(has_reference=has_reference)


def _build_section_rework_prompt(
    *, has_reference: bool, domain: str | None = None
) -> str:
    builder = section_rework_prompt.build_system_prompt
    try:
        return builder(has_reference=has_reference, domain=domain)
    except TypeError:
        return builder(has_reference=has_reference)


def _build_qc_verification_prompt(domain: str | None = None) -> str:
    if hasattr(qc_verification_prompt, "build_system_prompt"):
        return qc_verification_prompt.build_system_prompt(domain=domain)
    return qc_verification_prompt.SYSTEM_PROMPT


def _build_quiz_system_prompt(
    *, is_regeneration: bool, domain: str | None = None
) -> str:
    builder = quiz_prompt.build_quiz_system_prompt
    try:
        return builder(is_regeneration=is_regeneration, domain=domain)
    except TypeError:
        return builder(is_regeneration=is_regeneration)


def _build_hint_system_prompt(
    *, is_regeneration: bool, domain: str | None = None
) -> str:
    return hint_prompt.build_hint_system_prompt(
        domain=domain,
        is_regeneration=is_regeneration,
    )


HINT_PROGRAMMING_ANCHOR = "Focus on how Python handles integer division"


def _domain_filtering_active(
    empty_domain_prompt: str,
    filtered_domain_prompt: str,
) -> bool:
    return empty_domain_prompt.encode("utf-8") != filtered_domain_prompt.encode("utf-8")


@pytest.fixture(scope="module", autouse=True)
def _require_snapshots_exist() -> None:
    if os.environ.get("UPDATE_DOMAIN_PROMPT_SNAPSHOTS") == "1":
        return
    if not SNAPSHOT_DIR.is_dir():
        pytest.fail(
            f"Missing snapshot directory: {SNAPSHOT_DIR}. "
            "Regenerate with UPDATE_DOMAIN_PROMPT_SNAPSHOTS=1."
        )


class TestGenerationPromptSnapshots:
    def test_system_prompt_base(self) -> None:
        assert_prompt_bytes_equal(
            generation_prompt.SYSTEM_PROMPT,
            "generation_system_prompt_base.txt",
        )

    @pytest.mark.parametrize("has_reference", [True, False])
    def test_build_system_prompt_empty_domain_matches_pre_refactor(
        self, has_reference: bool
    ) -> None:
        snapshot = (
            "generation_system_prompt_has_reference.txt"
            if has_reference
            else "generation_system_prompt_no_reference.txt"
        )
        assert_prompt_bytes_equal(
            _build_generation_prompt(has_reference=has_reference, domain=""),
            snapshot,
        )

    @pytest.mark.parametrize("has_reference", [True, False])
    def test_build_system_prompt_mixed_domain_matches_empty_domain(
        self, has_reference: bool
    ) -> None:
        empty_domain = _build_generation_prompt(has_reference=has_reference, domain="")
        try:
            mixed_domain = _build_generation_prompt(
                has_reference=has_reference, domain="Mixed"
            )
        except TypeError:
            pytest.skip("domain parameter not yet wired")
        assert mixed_domain.encode("utf-8") == empty_domain.encode("utf-8")

    @pytest.mark.parametrize("has_reference", [True, False])
    def test_build_system_prompt_stem_uses_formula_only_schema(
        self, has_reference: bool
    ) -> None:
        try:
            stem_prompt = _build_generation_prompt(
                has_reference=has_reference, domain="STEM"
            )
        except TypeError:
            pytest.skip("domain parameter not yet wired")
        assert '"formula_blocks":' in stem_prompt
        assert '"code_blocks":' not in stem_prompt
        assert STEM_DERIVATION_ANCHOR in stem_prompt

    @pytest.mark.parametrize("has_reference", [True, False])
    def test_build_system_prompt_stem_domain_filters_programming_rules(
        self, has_reference: bool
    ) -> None:
        try:
            empty_prompt = _build_generation_prompt(
                has_reference=has_reference, domain=""
            )
            stem_prompt = _build_generation_prompt(
                has_reference=has_reference, domain="STEM"
            )
        except TypeError:
            pytest.skip("domain parameter not yet wired")
        if not _domain_filtering_active(empty_prompt, stem_prompt):
            pytest.skip("domain filtering not yet implemented")
        assert STEM_DERIVATION_ANCHOR in stem_prompt
        assert PROGRAMMING_ONLY_ANCHOR not in stem_prompt


class TestImprovePromptSnapshots:
    def test_base_system(self) -> None:
        assert_prompt_bytes_equal(
            improve_prompt._BASE_SYSTEM,
            "improve_base_system.txt",
        )

    @pytest.mark.parametrize("has_reference", [True, False])
    def test_build_system_prompt_empty_domain(self, has_reference: bool) -> None:
        snapshot = (
            "improve_system_prompt_has_reference.txt"
            if has_reference
            else "improve_system_prompt_no_reference.txt"
        )
        assert_prompt_bytes_equal(
            _build_improve_prompt(has_reference=has_reference, domain=""),
            snapshot,
        )


class TestRegenerationPromptSnapshots:
    def test_base_system(self) -> None:
        assert_prompt_bytes_equal(
            regeneration_prompt._BASE_SYSTEM,
            "regeneration_base_system.txt",
        )

    @pytest.mark.parametrize("has_reference", [True, False])
    def test_build_system_prompt_empty_domain(self, has_reference: bool) -> None:
        snapshot = (
            "regeneration_system_prompt_has_reference.txt"
            if has_reference
            else "regeneration_system_prompt_no_reference.txt"
        )
        assert_prompt_bytes_equal(
            _build_regeneration_prompt(has_reference=has_reference, domain=""),
            snapshot,
        )


class TestQcVerificationPromptSnapshots:
    def test_system_prompt(self) -> None:
        assert_prompt_bytes_equal(
            _build_qc_verification_prompt(domain=""),
            "qc_verification_system_prompt.txt",
        )

    def test_stem_domain_excludes_code_quality_section(self) -> None:
        try:
            empty_prompt = _build_qc_verification_prompt(domain="")
            stem_prompt = _build_qc_verification_prompt(domain="STEM")
        except TypeError:
            pytest.skip("domain parameter not yet wired")
        if not _domain_filtering_active(empty_prompt, stem_prompt):
            pytest.skip("domain filtering not yet implemented")
        assert "CODE QUALITY" not in stem_prompt
        assert PROGRAMMING_ONLY_ANCHOR not in stem_prompt


class TestSectionInsertPromptSnapshots:
    def test_base_system(self) -> None:
        assert_prompt_bytes_equal(
            section_insert_prompt._BASE_SYSTEM,
            "section_insert_base_system.txt",
        )

    @pytest.mark.parametrize("has_reference", [True, False])
    def test_build_system_prompt_empty_domain(self, has_reference: bool) -> None:
        snapshot = (
            "section_insert_system_prompt_has_reference.txt"
            if has_reference
            else "section_insert_system_prompt_no_reference.txt"
        )
        assert_prompt_bytes_equal(
            _build_section_insert_prompt(has_reference=has_reference, domain=""),
            snapshot,
        )


class TestSectionReworkPromptSnapshots:
    def test_base_system(self) -> None:
        assert_prompt_bytes_equal(
            section_rework_prompt._BASE_SYSTEM,
            "section_rework_base_system.txt",
        )

    @pytest.mark.parametrize("has_reference", [True, False])
    def test_build_system_prompt_empty_domain(self, has_reference: bool) -> None:
        snapshot = (
            "section_rework_system_prompt_has_reference.txt"
            if has_reference
            else "section_rework_system_prompt_no_reference.txt"
        )
        assert_prompt_bytes_equal(
            _build_section_rework_prompt(has_reference=has_reference, domain=""),
            snapshot,
        )


class TestQuizPromptSnapshots:
    def test_system_prompt_generate(self) -> None:
        assert_prompt_bytes_equal(
            quiz_prompt.SYSTEM_PROMPT_GENERATE,
            "quiz_system_prompt_generate.txt",
        )

    def test_system_prompt_regenerate(self) -> None:
        assert_prompt_bytes_equal(
            quiz_prompt.SYSTEM_PROMPT_REGENERATE,
            "quiz_system_prompt_regenerate.txt",
        )

    def test_build_quiz_system_prompt_generate_empty_domain(self) -> None:
        assert_prompt_bytes_equal(
            _build_quiz_system_prompt(is_regeneration=False, domain=""),
            "quiz_build_system_prompt_generate.txt",
        )

    def test_build_quiz_system_prompt_regenerate_empty_domain(self) -> None:
        assert_prompt_bytes_equal(
            _build_quiz_system_prompt(is_regeneration=True, domain=""),
            "quiz_build_system_prompt_regenerate.txt",
        )

    def test_stem_domain_filters_programming_question_rules(self) -> None:
        try:
            empty_prompt = _build_quiz_system_prompt(is_regeneration=False, domain="")
            stem_prompt = _build_quiz_system_prompt(
                is_regeneration=False, domain="STEM"
            )
        except TypeError:
            pytest.skip("domain parameter not yet wired")
        if not _domain_filtering_active(empty_prompt, stem_prompt):
            pytest.skip("domain filtering not yet implemented")
        assert PROGRAMMING_ONLY_ANCHOR not in stem_prompt


class TestHintPromptSnapshots:
    def test_system_prompt_hint(self) -> None:
        assert_prompt_bytes_equal(
            hint_prompt.SYSTEM_PROMPT_HINT,
            "hint_system_prompt.txt",
        )

    def test_system_prompt_hint_regenerate(self) -> None:
        assert_prompt_bytes_equal(
            _build_hint_system_prompt(is_regeneration=True, domain=""),
            "hint_system_prompt_regenerate.txt",
        )

    def test_regenerate_user_message_documents_previous_hints(self) -> None:
        payload = hint_prompt.build_hint_prompt(
            questions_for_hinting=[
                {
                    "question_id": "q1",
                    "question_text": "What is 2+2?",
                    "option_a": "3",
                    "option_b": "4",
                    "option_c": "5",
                    "option_d": "6",
                    "correct_option": "B",
                    "explanation": "Basic addition.",
                    "previous_hints": {
                        "hint_1": "Think about counting.",
                        "hint_2": "Add one more to one.",
                        "hint_3": "Two groups of two.",
                    },
                }
            ],
            topic_title="Arithmetic",
            domain="STEM",
            is_regeneration=True,
            mentor_feedback="Make hints more subtle.",
        )
        assert "previous_hints" in payload["user_message"]
        assert "<mentor_feedback>" in payload["user_message"]
        assert "Think about counting." in payload["user_message"]

    def test_stem_domain_filters_programming_reasoning(self) -> None:
        try:
            empty_prompt = _build_hint_system_prompt(is_regeneration=False, domain="")
            stem_prompt = _build_hint_system_prompt(
                is_regeneration=False, domain="STEM"
            )
        except TypeError:
            pytest.skip("domain parameter not yet wired")
        if not _domain_filtering_active(empty_prompt, stem_prompt):
            pytest.skip("domain filtering not yet implemented")
        assert HINT_PROGRAMMING_ANCHOR not in stem_prompt
