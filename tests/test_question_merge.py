# tests/test_question_merge.py
"""Unit tests for quiz question merge helpers."""

from __future__ import annotations

from uuid import uuid4

from src.api.utils.quiz_utils.quality_check_utils.document.question_merge import (
    bind_patch_question_ids,
    insert_questions,
    merge_full_regeneration_preserving_passing,
    merge_question_patches,
    prepare_question_patches_for_merge,
)


def _question(question_id: str, text: str, order_index: int) -> dict:
    return {
        "question_id": question_id,
        "question_text": text,
        "option_a": "A",
        "option_b": "B",
        "option_c": "C",
        "option_d": "D",
        "correct_option": "A",
        "explanation": "Because A.",
        "order_index": order_index,
    }


class TestMergeQuestionPatches:
    def test_patch_by_id_preserves_order(self):
        existing = [
            _question("q1", "Old 1", 0),
            _question("q2", "Old 2", 1),
        ]
        patch = [_question("q2", "New 2", 99)]
        result = merge_question_patches(existing, patch)
        assert result.questions[1]["question_text"] == "New 2"
        assert result.questions[1]["order_index"] == 1


class TestInsertQuestions:
    def test_insert_appends_and_assigns_ids(self):
        existing = [_question("q1", "Q1", 0)]
        new = [
            {
                "question_text": "Inserted?",
                "option_a": "A",
                "option_b": "B",
                "correct_option": "A",
                "explanation": "Because A.",
            }
        ]
        merged = insert_questions(existing, new)
        assert len(merged) == 2
        assert merged[1]["order_index"] == 1
        assert merged[1]["question_id"]


class TestMergeFullRegenerationPreservingPassing:
    def test_preserves_passing_questions(self):
        previous = [
            _question("q1", "Keep me", 0),
            _question("q2", "Rewrite me", 1),
        ]
        new = [
            _question("q1", "Should not replace", 0),
            _question("q2", "Rewritten", 1),
        ]
        merged = merge_full_regeneration_preserving_passing(
            new,
            previous,
            rewrite_question_ids={"q2"},
        )
        assert merged[0]["question_text"] == "Keep me"
        assert merged[1]["question_text"] == "Rewritten"

    def test_disjoint_ids_do_not_accumulate_extra_questions(self):
        previous = [
            _question("q1", "Keep me", 0),
            _question("q2", "Rewrite me", 1),
        ]
        new = [
            _question("fresh-1", "Keep me copy", 0),
            _question("fresh-2", "Rewritten 2", 1),
        ]
        merged = merge_full_regeneration_preserving_passing(
            new,
            previous,
            rewrite_question_ids={"q2"},
        )
        assert len(merged) == 2
        assert merged[0]["question_text"] == "Keep me"
        assert merged[1]["question_text"] == "Rewritten 2"
        assert merged[1]["question_id"] == "q2"


class TestBindPatchQuestionIds:
    def test_binds_single_patch_without_id(self):
        bound = bind_patch_question_ids(
            [{"question_text": "Fixed?", "option_a": "A"}],
            ["q7"],
        )
        assert bound[0]["question_id"] == "q7"


class TestPrepareQuestionPatchesForMerge:
    def test_full_quiz_response_replaces_only_failed_slot(self):
        existing = [
            _question("q1", "Keep 1", 0),
            _question("q2", "Keep 2", 1),
            _question("q3", "Broken", 2),
        ]
        patches = [_question("", f"New {index}", index) for index in range(3)]
        merged = prepare_question_patches_for_merge(
            existing,
            patches,
            target_question_ids=["q3"],
        )
        assert len(merged) == 3
        assert merged[0]["question_text"] == "Keep 1"
        assert merged[1]["question_text"] == "Keep 2"
        assert merged[2]["question_text"] == "New 2"
        assert merged[2]["question_id"] == "q3"

    def test_parser_assigned_uuids_do_not_block_targeted_patch(self):
        existing = [
            _question("q1", "Keep 1", 0),
            _question("q2", "Keep 2", 1),
            _question("q3", "Broken", 2),
        ]
        patches = [
            {
                **_question(str(uuid4()), f"Parser {index}", index),
                "correct_option": "D" if index == 2 else "A",
            }
            for index in range(3)
        ]
        merged = prepare_question_patches_for_merge(
            existing,
            patches,
            target_question_ids=["q3"],
        )
        assert len(merged) == 3
        assert merged[2]["question_id"] == "q3"
        assert merged[2]["correct_option"] == "D"
        assert merged[0]["question_text"] == "Keep 1"
