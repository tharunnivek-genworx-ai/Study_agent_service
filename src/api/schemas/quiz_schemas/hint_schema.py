# src/api/schemas/quiz_schemas/hint_schema.py
"""
Schemas for hint generation on existing quiz questions.

Hint lifecycle (separate from quiz question generation):
  1. Mentor finalizes quiz draft (questions stored without hints).
  2. Mentor triggers hint generation → Hint Agent LLM writes hint_1, hint_2,
     hint_3 onto existing quiz_questions rows.
  3. Mentor may selectively regenerate hints after editing specific questions.

The quiz row must already exist before hint generation can run.
"""

from typing import Literal, Self
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


class HintGenerateRequest(BaseModel):
    """
    Body for POST /nodes/:id/quizzes/:quiz_id/hints/generate.

    Generates hints for all active questions in the quiz that are missing
    at least one hint field. The quiz must exist and remain unpublished.
    No body fields are required — the quiz is identified from the path.
    """

    pass


class HintRegenerateRequest(BaseModel):
    """
    Body for POST /nodes/:id/quizzes/:quiz_id/hints/regenerate.

    Regenerates hints for active questions (selective subset or whole quiz).

    scope='selective' (default): question_ids is required; mentor_feedback is optional.
    scope='all': server resolves every active question with complete hints;
    mentor_feedback is required (min 10 characters).
    """

    scope: Literal["all", "selective"] = Field(
        default="selective",
        description=(
            "'selective' for explicit question_ids; 'all' for every active "
            "question that already has hints."
        ),
    )
    question_ids: list[UUID] | None = Field(
        default=None,
        description="Required when scope='selective'. Active question_ids to regenerate.",
    )
    mentor_feedback: str | None = Field(
        default=None,
        max_length=4000,
        description=(
            "Mentor instructions to steer regenerated hints. Required when scope='all'."
        ),
    )

    @model_validator(mode="after")
    def validate_scope_fields(self) -> Self:
        if self.scope == "selective":
            if not self.question_ids:
                raise ValueError("question_ids is required when scope='selective'.")
        elif self.scope == "all":
            feedback = (self.mentor_feedback or "").strip()
            if len(feedback) < 10:
                raise ValueError(
                    "mentor_feedback is required (min 10 characters) when scope='all'."
                )
        return self
