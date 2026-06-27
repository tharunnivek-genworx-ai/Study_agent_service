"""Merge question patches and insert new questions into a quiz."""

from __future__ import annotations

import copy
import logging
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

logger = logging.getLogger(__name__)


@dataclass
class MergeQuestionPatchesResult:
    questions: list[dict[str, Any]]
    unmatched_patch_ids: list[str] = field(default_factory=list)


def _question_id(question: dict[str, Any]) -> str:
    return str(question.get("question_id", "")).strip()


def _reindex_questions(questions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    reindexed: list[dict[str, Any]] = []
    for index, question in enumerate(questions):
        updated = copy.deepcopy(question)
        updated["order_index"] = index
        reindexed.append(updated)
    return reindexed


def merge_question_patches(
    questions: list[dict[str, Any]],
    patches: list[dict[str, Any]],
) -> MergeQuestionPatchesResult:
    """Replace questions whose question_id matches a patch object."""
    merged = copy.deepcopy(questions)
    index_by_id = {
        _question_id(question): index
        for index, question in enumerate(merged)
        if _question_id(question)
    }

    unmatched: list[str] = []
    for patch in patches:
        if not isinstance(patch, dict):
            continue
        patch_id = _question_id(patch)
        if not patch_id:
            continue
        if patch_id in index_by_id:
            existing = merged[index_by_id[patch_id]]
            updated = copy.deepcopy(patch)
            updated["question_id"] = patch_id
            updated["order_index"] = existing.get("order_index", index_by_id[patch_id])
            merged[index_by_id[patch_id]] = updated
        else:
            unmatched.append(patch_id)
            logger.warning("Question patch id %s not found in quiz", patch_id)

    return MergeQuestionPatchesResult(
        questions=_reindex_questions(merged),
        unmatched_patch_ids=unmatched,
    )


def insert_questions(
    questions: list[dict[str, Any]],
    new_questions: list[dict[str, Any]],
    *,
    after_question_id: str | None = None,
) -> list[dict[str, Any]]:
    """Insert new questions, assigning question_id and order_index on merge."""
    merged = copy.deepcopy(questions)
    ordered_new = [q for q in new_questions if isinstance(q, dict)]

    for new_question in ordered_new:
        updated = copy.deepcopy(new_question)
        if not _question_id(updated):
            updated["question_id"] = str(uuid4())
        if after_question_id:
            anchor = str(after_question_id).strip()
            insert_at = next(
                (
                    index + 1
                    for index, question in enumerate(merged)
                    if _question_id(question) == anchor
                ),
                len(merged),
            )
        else:
            insert_at = len(merged)
        merged.insert(insert_at, updated)

    return _reindex_questions(merged)


def extract_questions_by_ids(
    questions: list[dict[str, Any]],
    ids: list[str],
) -> list[dict[str, Any]]:
    """Return question dicts whose question_id is in ids, preserving ids order."""
    wanted = {
        str(question_id).strip() for question_id in ids if str(question_id).strip()
    }
    if not wanted:
        return []

    by_id = {
        _question_id(question): copy.deepcopy(question)
        for question in questions
        if _question_id(question)
    }
    ordered: list[dict[str, Any]] = []
    for raw_id in ids:
        normalized = str(raw_id).strip()
        if normalized in by_id:
            ordered.append(by_id[normalized])
    return ordered


def merge_full_regeneration_preserving_passing(
    new_questions: list[dict[str, Any]],
    previous_questions: list[dict[str, Any]],
    *,
    rewrite_question_ids: set[str] | frozenset[str],
) -> list[dict[str, Any]]:
    """Keep passing questions from previous quiz; take rewrites from new output."""
    rewrite_ids = {
        str(question_id).strip()
        for question_id in rewrite_question_ids
        if str(question_id).strip()
    }
    previous_by_id = {
        _question_id(question): copy.deepcopy(question)
        for question in previous_questions
        if _question_id(question)
    }
    new_by_id = {
        _question_id(question): copy.deepcopy(question)
        for question in new_questions
        if _question_id(question)
    }

    ordered_ids: list[str] = []
    seen: set[str] = set()
    for question in previous_questions:
        qid = _question_id(question)
        if qid and qid not in seen:
            seen.add(qid)
            ordered_ids.append(qid)
    for question in new_questions:
        qid = _question_id(question)
        if qid and qid not in seen:
            seen.add(qid)
            ordered_ids.append(qid)

    merged: list[dict[str, Any]] = []
    for question_id in ordered_ids:
        if question_id in rewrite_ids:
            question = new_by_id.get(question_id) or previous_by_id.get(question_id)
        else:
            question = previous_by_id.get(question_id) or new_by_id.get(question_id)
        if question is not None:
            merged.append(question)

    merged_ids = {_question_id(question) for question in merged}
    for question_id, question in new_by_id.items():
        if question_id not in merged_ids:
            merged.append(question)

    return _reindex_questions(merged)
