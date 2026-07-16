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


def bind_patch_question_ids(
    patches: list[dict[str, Any]],
    target_question_ids: list[str],
) -> list[dict[str, Any]]:
    """Attach ``question_id`` values to patch objects when the LLM omitted them.

    When the patch count matches the failed-question count (or there is a single
    patch for a single failure), ids are assigned in ``target_question_ids`` order.
    """
    bound: list[dict[str, Any]] = [
        copy.deepcopy(patch) for patch in patches if isinstance(patch, dict)
    ]
    if not bound or not target_question_ids:
        return bound

    normalized_targets = [
        str(question_id).strip()
        for question_id in target_question_ids
        if str(question_id).strip()
    ]
    if not normalized_targets:
        return bound

    existing_patch_ids = {_question_id(patch) for patch in bound if _question_id(patch)}
    if existing_patch_ids.intersection(normalized_targets):
        return bound

    if len(bound) == len(normalized_targets):
        for patch, target_id in zip(bound, normalized_targets, strict=False):
            patch["question_id"] = target_id
    elif len(bound) == 1 and len(normalized_targets) == 1:
        bound[0]["question_id"] = normalized_targets[0]

    return bound


def bind_patches_by_order_index(
    patches: list[dict[str, Any]],
    existing_questions: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Map a full-quiz patch response onto existing ids by ``order_index``."""
    sorted_existing = sorted(
        existing_questions,
        key=lambda question: question.get("order_index", 0),
    )
    sorted_patches = sorted(
        patches,
        key=lambda question: question.get("order_index", 0),
    )
    if len(sorted_patches) != len(sorted_existing):
        return [copy.deepcopy(patch) for patch in sorted_patches]

    bound: list[dict[str, Any]] = []
    for patch, existing in zip(sorted_patches, sorted_existing, strict=False):
        updated = copy.deepcopy(patch)
        updated["question_id"] = _question_id(existing)
        updated["order_index"] = existing.get("order_index")
        bound.append(updated)
    return bound


def _existing_question_ids(questions: list[dict[str, Any]]) -> set[str]:
    return {_question_id(question) for question in questions if _question_id(question)}


def _strip_unrecognized_patch_ids(
    patches: list[dict[str, Any]],
    existing_ids: set[str],
) -> list[dict[str, Any]]:
    """Remove parser-assigned ids that do not belong to the live quiz."""
    stripped: list[dict[str, Any]] = []
    for patch in patches:
        if not isinstance(patch, dict):
            continue
        updated = copy.deepcopy(patch)
        patch_id = _question_id(updated)
        if patch_id and patch_id not in existing_ids:
            updated.pop("question_id", None)
        stripped.append(updated)
    return stripped


def _normalize_patch_payload(
    patches: list[dict[str, Any]],
    *,
    existing_questions: list[dict[str, Any]],
    ordered_targets: list[str],
    id_set: set[str],
) -> list[dict[str, Any]]:
    """Bind patch objects to quiz ids before merge."""
    existing_ids = _existing_question_ids(existing_questions)
    bound = bind_patch_question_ids(patches, ordered_targets)
    patch_ids = {_question_id(patch) for patch in bound if _question_id(patch)}

    if patch_ids and patch_ids.issubset(existing_ids):
        if ordered_targets:
            targeted = [patch for patch in bound if _question_id(patch) in id_set]
            return targeted or bound
        return bound

    stripped = _strip_unrecognized_patch_ids(patches, existing_ids)

    if len(ordered_targets) == 1 and len(stripped) > 1:
        failed_id = ordered_targets[0]
        sorted_existing = sorted(
            existing_questions,
            key=lambda question: question.get("order_index", 0),
        )
        failed_index = next(
            (
                index
                for index, question in enumerate(sorted_existing)
                if _question_id(question) == failed_id
            ),
            None,
        )
        sorted_patches = sorted(
            stripped,
            key=lambda question: question.get("order_index", 0),
        )
        if failed_index is not None and failed_index < len(sorted_patches):
            return bind_patch_question_ids(
                [sorted_patches[failed_index]],
                ordered_targets,
            )

    rebound = bind_patch_question_ids(stripped, ordered_targets)
    rebound_ids = {_question_id(patch) for patch in rebound if _question_id(patch)}
    if rebound_ids and rebound_ids.issubset(existing_ids):
        if ordered_targets:
            targeted = [patch for patch in rebound if _question_id(patch) in id_set]
            return targeted or rebound
        return rebound

    if len(stripped) == len(existing_questions):
        positional = bind_patches_by_order_index(stripped, existing_questions)
        if ordered_targets:
            return [patch for patch in positional if _question_id(patch) in id_set]
        return positional

    return rebound


def prepare_question_patches_for_merge(
    existing_questions: list[dict[str, Any]],
    patches: list[dict[str, Any]],
    *,
    target_question_ids: list[str],
) -> list[dict[str, Any]]:
    """Normalize patch payloads so ``merge_question_patches`` can apply them.

    Handles the common LLM failure modes:
    - patch objects missing ``question_id`` (bound to QC failure targets)
    - full-quiz rewrite returned when only targeted fixes were requested
    """
    if not patches:
        return copy.deepcopy(existing_questions)

    id_set = {
        str(question_id).strip()
        for question_id in target_question_ids
        if str(question_id).strip()
    }
    sorted_existing = sorted(
        existing_questions,
        key=lambda item: item.get("order_index", 0),
    )
    ordered_targets = [
        _question_id(question)
        for question in sorted_existing
        if _question_id(question) in id_set
    ]

    prepared = _normalize_patch_payload(
        patches,
        existing_questions=sorted_existing,
        ordered_targets=ordered_targets,
        id_set=id_set,
    )
    if not prepared:
        logger.warning("Question patch payload could not be bound to quiz ids")
        return copy.deepcopy(existing_questions)

    if (
        len(patches) == len(existing_questions)
        and ordered_targets
        and len(ordered_targets) < len(existing_questions)
    ):
        logger.warning(
            "Patch response matched full quiz length; applying only targeted ids: %s",
            ", ".join(ordered_targets),
        )

    merge_result = merge_question_patches(existing_questions, prepared)
    if merge_result.unmatched_patch_ids:
        logger.warning(
            "Unmatched question patch ids after binding: %s",
            ", ".join(merge_result.unmatched_patch_ids),
        )
    return merge_result.questions


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


def remove_questions_by_ids(
    questions: list[dict[str, Any]],
    remove_ids: list[str] | set[str],
) -> list[dict[str, Any]]:
    """Drop questions whose question_id is in ``remove_ids`` and reindex."""
    wanted_removed = {
        str(question_id).strip()
        for question_id in remove_ids
        if str(question_id).strip()
    }
    if not wanted_removed:
        return _reindex_questions(copy.deepcopy(questions))
    kept = [
        copy.deepcopy(question)
        for question in questions
        if _question_id(question) not in wanted_removed
    ]
    return _reindex_questions(kept)


def prune_questions_to_count(
    questions: list[dict[str, Any]],
    expected_count: int,
    *,
    prefer_remove_ids: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Reduce quiz length to ``expected_count`` without LLM.

    Removal priority:
    1. ``prefer_remove_ids`` (e.g. previously failing / QC-flagged questions)
    2. Newest questions (highest ``order_index`` / list tail — typically inserts)
    """
    if expected_count < 0:
        expected_count = 0
    if len(questions) <= expected_count:
        return _reindex_questions(copy.deepcopy(questions))

    excess = len(questions) - expected_count
    prefer = {
        str(question_id).strip()
        for question_id in (prefer_remove_ids or [])
        if str(question_id).strip()
    }
    remove_ids: list[str] = []
    for question in questions:
        question_id = _question_id(question)
        if question_id and question_id in prefer:
            remove_ids.append(question_id)
            if len(remove_ids) >= excess:
                break

    if len(remove_ids) < excess:
        for question in reversed(questions):
            question_id = _question_id(question)
            if not question_id or question_id in remove_ids:
                continue
            remove_ids.append(question_id)
            if len(remove_ids) >= excess:
                break

    return remove_questions_by_ids(questions, remove_ids)


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


def _merge_full_regeneration_positional(
    new_questions: list[dict[str, Any]],
    previous_questions: list[dict[str, Any]],
    *,
    rewrite_ids: set[str],
) -> list[dict[str, Any]] | None:
    """Splice new questions onto rewrite slots when ids are not preserved."""
    sorted_previous = sorted(
        previous_questions,
        key=lambda question: question.get("order_index", 0),
    )
    sorted_new = sorted(
        new_questions,
        key=lambda question: question.get("order_index", 0),
    )
    if not sorted_previous or not sorted_new:
        return None

    if len(sorted_new) == len(sorted_previous):
        merged: list[dict[str, Any]] = []
        for index, previous in enumerate(sorted_previous):
            previous_id = _question_id(previous)
            if previous_id in rewrite_ids and index < len(sorted_new):
                updated = copy.deepcopy(sorted_new[index])
                updated["question_id"] = previous_id
                updated["order_index"] = previous.get("order_index", index)
                merged.append(updated)
            else:
                merged.append(copy.deepcopy(previous))
        return _reindex_questions(merged)

    if len(sorted_new) == len(rewrite_ids):
        rewrite_ordered = [
            _question_id(question)
            for question in sorted_previous
            if _question_id(question) in rewrite_ids
        ]
        merged = copy.deepcopy(sorted_previous)
        for question_id, new_question in zip(
            rewrite_ordered,
            sorted_new,
            strict=False,
        ):
            index = next(
                idx
                for idx, question in enumerate(merged)
                if _question_id(question) == question_id
            )
            updated = copy.deepcopy(new_question)
            updated["question_id"] = question_id
            updated["order_index"] = merged[index].get("order_index", index)
            merged[index] = updated
        return _reindex_questions(merged)

    return None


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

    previous_ids = set(previous_by_id.keys())
    new_ids = set(new_by_id.keys())
    if new_ids.isdisjoint(previous_ids):
        positional = _merge_full_regeneration_positional(
            new_questions,
            previous_questions,
            rewrite_ids=rewrite_ids,
        )
        if positional is not None:
            return positional
        logger.warning(
            "Full-regeneration output used fresh question_ids; replacing quiz "
            "by order_index to avoid duplicate accumulation"
        )
        return bind_patches_by_order_index(new_questions, previous_questions)

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

    return _reindex_questions(merged)
