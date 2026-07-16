"""Regression tests for published quiz question immutability."""

from types import SimpleNamespace

import pytest

from src.api.core.exceptions import QuizAlreadyPublishedException
from src.api.core.services.quiz_services.quiz_service import (
    _assert_quiz_questions_mutable,
)
from src.api.utils.quiz_utils.mentor_quiz_ui import compute_mentor_quiz_ui_flags


def test_draft_quiz_questions_are_mutable() -> None:
    _assert_quiz_questions_mutable(SimpleNamespace(is_published=False))


def test_published_quiz_questions_are_immutable() -> None:
    with pytest.raises(QuizAlreadyPublishedException) as exc_info:
        _assert_quiz_questions_mutable(SimpleNamespace(is_published=True))

    assert exc_info.value.status_code == 409


def test_empty_draft_allows_first_manual_question() -> None:
    flags = compute_mentor_quiz_ui_flags(
        published=None,
        quiz_row=SimpleNamespace(
            is_published=False,
            total_questions=0,
            study_material_version_id=None,
        ),
    )

    assert flags["can_edit_questions"] is True
    assert flags["can_regenerate_quiz"] is False
