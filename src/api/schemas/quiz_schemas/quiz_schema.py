# src/api/schemas/content_schemas/quiz_schema.py
"""
Schemas for quizzes, quiz_questions, quiz_attempts, quiz_question_responses.

Quiz lifecycle (TDD §3.2.2 and §3.2.3):
  1. Mentor triggers generation → new quizzes row + quiz_questions rows
     (all three hints are pre-generated at this point — no LLM calls during attempts).
  2. Mentor optionally edits/deletes questions.
  3. Mentor publishes quiz → is_published=TRUE, visible to trainees.
  4. Trainee starts attempt → quiz_attempts row (status='in_progress').
  5. Per question: trainee submits/changes answer → quiz_question_responses row.
     Wrong answer increments hint_level_reached and reveals the next stored hint:
       hint_level_reached=0 → no hint shown yet
       hint_level_reached=1 → hint_1 revealed (1st wrong attempt) — subtle nudge
       hint_level_reached=2 → hint_2 revealed (2nd wrong attempt) — narrows reasoning
       hint_level_reached=3 → hint_3 revealed (3rd wrong attempt) — most explicit hint
     IMPORTANT: The correct answer is NEVER revealed automatically during a live attempt.
     explanation is for post-submit review only — it is NOT shown during the live attempt.
  6. Trainee submits attempt → score calculated; quiz_attempts.status='submitted'.
  7. Engagement & Chat Service receives completion signal and updates
     trainee_node_progress.quiz_best_score and quiz_passed.

Multiple quiz rows per node: old quizzes and their attempts are NEVER deleted.
When regenerated, a new quizzes row is created. Only the published quiz is
shown to trainees (filtered at query time by is_published=TRUE on the latest
quiz row for the node — service enforces this).

EC-10: Deleted questions (is_active=False) still appear in historical attempt
responses, labelled '(Removed)' by the frontend using is_active=False flag.
"""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

# ── Enums / Literals ─────────────────────────────────────────────────────────

QuizDifficulty = Literal["easy", "medium", "hard", "mixed"]
QuizAttemptStatus = Literal["in_progress", "submitted", "abandoned"]
CorrectOption = Literal["A", "B", "C", "D"]
QuestionSource = Literal["ai_generated", "mentor_manual"]


# ─────────────────────────────────────────────────────────────────────────────
# MENTOR-FACING: Quiz Generation & Management
# ─────────────────────────────────────────────────────────────────────────────


class QuizGenerateRequest(BaseModel):
    """
    Body for POST /nodes/:id/quizzes/generate.

    study_material_version_id is required — the Quiz Agent always generates
    from a specific published version, not from whatever happens to be active.
    This anchors the quiz to a known content snapshot, preserving audit lineage
    (EC-4: if content is regenerated, the quiz still references the version
    it was generated from).

    difficulty and title are optional; the LLM derives sensible defaults
    from the node title if not provided.

    All three hints (hint_1, hint_2, hint_3) are generated at this time.
    No LLM calls happen during trainee quiz attempts.
    """

    study_material_version_id: UUID = Field(
        ...,
        description=(
            "Must be a published (is_published=TRUE) version for this node. "
            "The Quiz Agent uses this version's content as primary LLM context."
        ),
    )
    difficulty: QuizDifficulty = Field(
        default="mixed",
        description="Desired difficulty level. 'mixed' lets the LLM vary question difficulty.",
    )
    title: str | None = Field(
        default=None,
        max_length=300,
        description="Optional quiz title. Auto-generated from node title if omitted.",
    )


class QuizPublishRequest(BaseModel):
    """
    Body for PATCH /nodes/:id/quizzes/:quiz_id/publish.
    No body fields needed — publish is an action on the quiz identified in the path.
    Kept as an explicit schema (rather than a bare PATCH with no body) so that
    future fields (e.g., scheduled_publish_at) can be added without a route change.
    """

    pass


class QuizQuestionCreateRequest(BaseModel):
    """
    Body for POST /nodes/:id/quizzes/:quiz_id/questions.
    Allows mentor to manually add a question to an existing quiz.
    source is forced to 'mentor_manual' at the service layer.

    option_c and option_d are Optional — 3-option questions are supported.
    correct_option must reference a non-None option (e.g., cannot set
    correct_option='D' if option_d is None) — validated at service layer.

    hint_1, hint_2, hint_3 are the three progressive hints:
      hint_1: subtle nudge (1st wrong attempt)
      hint_2: narrows reasoning (2nd wrong attempt)
      hint_3: most explicit hint — does NOT reveal the answer (3rd wrong attempt)
    explanation: post-submit review only; not revealed during a live attempt.
    """

    question_text: str = Field(..., min_length=5)
    option_a: str = Field(..., min_length=1)
    option_b: str = Field(..., min_length=1)
    option_c: str | None = None
    option_d: str | None = None
    correct_option: CorrectOption
    hint_1: str | None = None
    hint_2: str | None = None
    hint_3: str | None = None
    explanation: str | None = None
    order_index: int = Field(
        default=0,
        ge=0,
        description="Display position among siblings. Service appends to end if 0.",
    )


class QuizQuestionUpdateRequest(BaseModel):
    """
    Body for PATCH /nodes/:id/quizzes/:quiz_id/questions/:question_id.
    All fields are Optional — partial updates are supported.
    The service merges only the provided fields onto the existing row.

    Note: updating correct_option on a published quiz triggers a
    quiz_questions_edited node_event_notification (EC-12). The service
    handles this; the schema does not need to carry a flag for it.

    hint_3 is the most explicit hint — it must NOT reveal the correct answer.
    explanation is post-submit only and must NOT reveal the answer during a live attempt.
    """

    question_text: str | None = Field(default=None, min_length=5)
    option_a: str | None = None
    option_b: str | None = None
    option_c: str | None = None
    option_d: str | None = None
    correct_option: CorrectOption | None = None
    hint_1: str | None = None
    hint_2: str | None = None
    hint_3: str | None = None
    explanation: str | None = None
    order_index: int | None = Field(default=None, ge=0)


class QuizQuestionReorderRequest(BaseModel):
    """
    Body for PATCH /nodes/:id/quizzes/:quiz_id/questions/reorder.
    question_ids must be the complete set of active questions for the quiz.
    Partial reorders are rejected — same guard as node and media reorders.
    """

    question_ids: list[UUID] = Field(
        ...,
        min_length=1,
        description="All active question_ids in desired display order.",
    )


# ─────────────────────────────────────────────────────────────────────────────
# MENTOR-FACING: Response Schemas
# ─────────────────────────────────────────────────────────────────────────────


class QuizQuestionOut(BaseModel):
    """
    Full question row, mentor-facing.
    Exposes correct_option, all three hints, and explanation — all of which
    are hidden from trainees until the appropriate hint_level_reached threshold
    is met or the attempt is submitted.
    """

    model_config = ConfigDict(from_attributes=True)

    question_id: UUID
    quiz_id: UUID
    node_id: UUID
    question_text: str
    option_a: str
    option_b: str
    option_c: str | None
    option_d: str | None
    correct_option: CorrectOption
    hint_1: str | None
    hint_2: str | None
    hint_3: str | None
    explanation: str | None
    order_index: int
    is_active: bool
    source: QuestionSource
    created_at: datetime


class QuizOut(BaseModel):
    """
    Full quiz row with its questions. Returned after generation, publish,
    and on GET /nodes/:id/quizzes/:quiz_id (mentor route).
    total_questions reflects the count of is_active=TRUE questions only —
    it is updated by the service whenever questions are added or soft-deleted.
    """

    model_config = ConfigDict(from_attributes=True)

    quiz_id: UUID
    node_id: UUID
    space_id: UUID
    study_material_version_id: UUID
    title: str
    total_questions: int
    difficulty: QuizDifficulty
    is_published: bool
    published_at: datetime | None
    created_by: UUID
    created_at: datetime
    updated_at: datetime
    questions: list[QuizQuestionOut]


class QuizSummaryOut(BaseModel):
    """
    Lightweight quiz row without questions. Used in list endpoints
    (GET /nodes/:id/quizzes) to show all quiz generations for the node
    without loading every question set.
    """

    model_config = ConfigDict(from_attributes=True)

    quiz_id: UUID
    node_id: UUID
    space_id: UUID
    study_material_version_id: UUID
    title: str
    total_questions: int
    difficulty: QuizDifficulty
    is_published: bool
    published_at: datetime | None
    created_at: datetime


class QuizListOut(BaseModel):
    """All quizzes for a node, ordered by created_at DESC (newest first)."""

    node_id: UUID
    quizzes: list[QuizSummaryOut]
    total: int


class QuizQuestionDeletedOut(BaseModel):
    """Confirmation after soft-delete of a question."""

    question_id: UUID
    deleted: bool = True
    message: str = "Question removed from quiz."


# ─────────────────────────────────────────────────────────────────────────────
# TRAINEE-FACING: Quiz Delivery Schemas
# ─────────────────────────────────────────────────────────────────────────────


class TraineeQuizQuestionOut(BaseModel):
    """
    Trainee-safe view of a single question during a live attempt.

    Progressive hint reveal — gated by hint_level_reached:
      0 → no hint shown
      1 → hint_1 revealed (subtle nudge)
      2 → hint_2 revealed (narrows reasoning)
      3 → hint_3 revealed (most explicit hint; does NOT reveal the answer)

    IMPORTANT — what is NEVER shown during a live attempt:
      - The correct answer (correct_option) is never exposed here.
      - explanation is post-submit only; it is served in a separate
        post-submission response, not in this live-attempt schema.

    The service merges the question row with the response row before building
    this response — the schema accepts Optional for all gated fields.

    hint_level_reached is echoed back so the frontend knows which hints to
    show without re-deriving it from attempt state.

    is_active=False means the mentor deleted this question after the attempt
    started — frontend should render it with '(Removed)' label (EC-10).
    """

    model_config = ConfigDict(from_attributes=True)

    question_id: UUID
    question_text: str
    option_a: str
    option_b: str
    option_c: str | None
    option_d: str | None
    is_active: bool
    order_index: int

    # Gated fields — populated by service when hint threshold is met
    hint_1: str | None = None  # revealed at hint_level_reached >= 1
    hint_2: str | None = None  # revealed at hint_level_reached >= 2
    hint_3: str | None = (
        None  # revealed at hint_level_reached >= 3 (does NOT reveal answer)
    )

    # Current attempt state for this question
    hint_level_reached: int
    was_skipped: bool
    was_locked: bool
    selected_option: str | None
    is_correct: bool | None


class TraineeQuizOut(BaseModel):
    """
    Full quiz view for a trainee mid-attempt.
    Returned on attempt start and resume. Contains all questions with
    their current attempt state merged in by the service.
    Does not expose correct answers or explanations — those are post-submit only.
    """

    quiz_id: UUID
    node_id: UUID
    title: str
    difficulty: QuizDifficulty
    total_questions: int
    attempt_id: UUID
    attempt_status: QuizAttemptStatus
    started_at: datetime
    questions: list[TraineeQuizQuestionOut]


class QuizAttemptStartRequest(BaseModel):
    """
    Body for POST /nodes/:id/quizzes/:quiz_id/attempt.
    No fields needed — the service derives trainee_id from the JWT,
    creates the quiz_attempts row, and returns the full quiz with
    blank attempt state.
    Kept as an explicit schema for future extensibility (e.g., attempt_mode).
    """

    pass


class QuizQuestionResponseRequest(BaseModel):
    """
    Body for POST/PATCH /attempts/:attempt_id/response.

    selected_option=None with was_skipped=True records a deliberate skip.
    selected_option set with was_skipped=False records an answer submission.
    The service increments hint_level_reached if the answer is wrong,
    and sets was_locked=True once the answer is correct (EC-7, EC-8).

    The service validates that was_locked=False before accepting an update —
    locked questions cannot be changed.
    """

    question_id: UUID
    selected_option: CorrectOption | None = Field(
        default=None,
        description="None when was_skipped=True.",
    )
    was_skipped: bool = Field(
        default=False,
        description="True records a deliberate skip. selected_option must be None.",
    )


class QuizAttemptSubmitRequest(BaseModel):
    """
    Body for POST /attempts/:attempt_id/submit.
    No fields needed — the service computes the score from existing
    quiz_question_responses rows for the attempt_id.
    Kept as an explicit schema for future extensibility.
    """

    pass


class QuizAttemptOut(BaseModel):
    """
    Returned after attempt submission (POST /attempts/:id/submit).
    score is a float 0.0–1.0 (e.g., 0.75 = 75%).
    The Engagement & Chat Service is notified separately to update
    trainee_node_progress — this response carries the raw attempt result only.
    """

    model_config = ConfigDict(from_attributes=True)

    attempt_id: UUID
    quiz_id: UUID
    node_id: UUID
    space_id: UUID
    trainee_id: UUID
    status: QuizAttemptStatus
    score: float | None
    total_correct: int | None
    total_with_hints: int | None
    total_skipped: int | None
    started_at: datetime
    submitted_at: datetime | None


class QuizQuestionResponseOut(BaseModel):
    """
    Returned after POST/PATCH /attempts/:id/response.
    Carries back the updated hint level and lock state so the frontend
    can immediately update the question navigator panel.

    hint_1/2/3 are populated by the service when the hint threshold is met.
    The correct answer is NEVER included here — it is post-submit only.
    explanation is also post-submit only and is NOT included here.
    """

    model_config = ConfigDict(from_attributes=True)

    response_id: UUID
    attempt_id: UUID
    question_id: UUID
    selected_option: str | None
    is_correct: bool | None
    hint_level_reached: int
    was_skipped: bool
    was_locked: bool
    # Gated hint fields populated by service when hint thresholds are met
    hint_1: str | None = None
    hint_2: str | None = None
    hint_3: str | None = None
