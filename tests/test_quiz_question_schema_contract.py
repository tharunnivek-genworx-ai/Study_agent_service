"""Contract tests for mentor-authored quiz question payloads."""

import pytest
from pydantic import ValidationError

from src.api.schemas.quiz_schemas.quiz_schema import QuizQuestionUpdateRequest


@pytest.mark.parametrize("field", ["option_a", "option_b", "option_c", "option_d"])
@pytest.mark.parametrize("invalid_value", [None, "", "   "])
def test_question_update_rejects_explicit_null_or_blank_option(
    field: str,
    invalid_value: str | None,
) -> None:
    with pytest.raises(ValidationError):
        QuizQuestionUpdateRequest(**{field: invalid_value})


def test_question_update_allows_omitted_options_for_partial_patch() -> None:
    payload = QuizQuestionUpdateRequest(question_text="Updated question text")

    assert payload.model_fields_set == {"question_text"}


@pytest.mark.parametrize(
    "field",
    [
        "question_text",
        "correct_option",
        "order_index",
    ],
)
def test_question_update_rejects_explicit_null_for_required_field(field: str) -> None:
    with pytest.raises(ValidationError):
        QuizQuestionUpdateRequest(**{field: None})
