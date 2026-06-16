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

from uuid import UUID

from pydantic import BaseModel, Field


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

    Regenerates hints for a specific subset of active questions (e.g. after
    the mentor edits question text or options during draft review).
    question_ids must all belong to the quiz and be is_active=True.
    """

    question_ids: list[UUID] = Field(
        ...,
        min_length=1,
        description="Active question_ids to regenerate hints for.",
    )
    mentor_feedback: str | None = Field(
        default=None,
        description="Optional mentor instructions to steer regenerated hints.",
    )
