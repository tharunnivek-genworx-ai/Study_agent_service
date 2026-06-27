# src/api/schemas/quiz_schemas/quiz_schema.py
"""
Schemas for quizzes, quiz_questions, quiz_attempts, quiz_question_responses.

Quiz lifecycle (TDD §3.2.2 and §3.2.3):
  1. Mentor triggers quiz generation → new quizzes row + quiz_questions rows
     (questions only — hints are NOT generated at this step).
  2. Mentor optionally edits/deletes questions.
  3. Mentor triggers hint generation → hint_1, hint_2, hint_3 written to
     existing quiz_questions rows (separate Hint Agent LangGraph flow).
  4. Mentor publishes quiz → is_published=TRUE, visible to trainees.
  5. Trainee starts attempt → quiz_attempts row (status='in_progress').
  6. Per question: trainee submits/changes answer → quiz_question_responses row.
     Wrong answer increments hint_level_reached and reveals the next stored hint:
       hint_level_reached=0 → no hint shown yet
       hint_level_reached=1 → hint_1 revealed (1st wrong attempt) — subtle nudge
       hint_level_reached=2 → hint_2 revealed (2nd wrong attempt) — narrows reasoning
       hint_level_reached=3 → hint_3 revealed (3rd wrong attempt) — most explicit hint
     IMPORTANT: The correct answer is NEVER revealed automatically during a live attempt.
     explanation is for post-submit review only — it is NOT shown during the live attempt.
  7. Trainee submits attempt → score calculated; quiz_attempts.status='submitted'.
  8. study_agent_service updates trainee_node_progress.quiz_best_score and
     quiz_passed on submit; EC-20 reset runs on quiz publish.

Multiple quiz rows per node: superseded/archived quizzes and their attempts are
retained. Regenerating uses one active draft per node (in-place when a draft
already exists). Only the active published quiz is shown to trainees.

EC-10: Deleted questions (is_active=False) still appear in historical attempt
responses, labelled '(Removed)' by the frontend using is_active=False flag.
"""

from datetime import datetime
from typing import Any, Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.api.schemas.common.generation_diagnostics_schema import (
    GenerationDiagnosticsOut,
    QualityCheckItemOut,
)
from src.api.schemas.study_material_schemas.study_material_schema import RetentionMode

# ── Enums / Literals ─────────────────────────────────────────────────────────

QuizDifficulty = Literal["easy", "medium", "hard", "mixed"]
QuizAttemptStatus = Literal["in_progress", "submitted", "abandoned"]
CorrectOption = Literal["A", "B", "C", "D"]
QuestionSource = Literal["ai_generated", "mentor_manual"]
QuestionNavStatus = Literal["notVisited", "visited", "answered", "skipped"]


class QuizQualityCheckScoresOut(BaseModel):
    """Individual dimension scores from the quiz QC evaluator."""

    answer_correctness: int | None = None
    question_quality: int | None = None
    topic_relevance: int | None = None
    option_quality: int | None = None
    question_clarity: int | None = None
    difficulty_alignment: int | None = None
    explanation_quality: int | None = None
    duplicate_overlap: int | None = None


class QuizQualityCheckFlaggedQuestionOut(BaseModel):
    """Flagged question entry in the quiz QC result."""

    question_id: UUID
    question_number: int
    flags: list[str] = Field(default_factory=list)


class QuizQualityCheckResultOut(BaseModel):
    """Structured quiz QC evaluation result surfaced to the frontend."""

    overall_status: Literal["pass", "warn", "fail"]
    wrong_answer_risk: Literal["none", "low", "medium", "high"]
    checks: list[QualityCheckItemOut] = Field(default_factory=list)
    issues: list[str] = Field(default_factory=list)
    corrective_instructions: str = ""
    summary: str = ""
    scores: QuizQualityCheckScoresOut | None = None
    flagged_questions: list[QuizQualityCheckFlaggedQuestionOut] | None = None
    retry_recommendation: dict[str, Any] | None = None


# ─────────────────────────────────────────────────────────────────────────────
# MENTOR-FACING: Quiz Generation & Management
# ─────────────────────────────────────────────────────────────────────────────


class QuizGenerateRequest(BaseModel):
    """
    Body for POST /nodes/:id/quizzes/generate.

    Generation always uses the node's currently published study material as
    source context (``study_material_version_id`` metadata is set server-side).
    """

    difficulty: QuizDifficulty = Field(
        default="mixed",
        description="Desired difficulty level. 'mixed' lets the LLM vary question difficulty.",
    )
    title: str | None = Field(
        default=None,
        max_length=300,
        description="Optional quiz title. Auto-generated from node title if omitted.",
    )
    question_count: int = Field(
        default=10,
        ge=5,
        le=20,
        description="Number of questions to generate.",
    )
    mode: str = Field(
        default="generate",
        description="'generate' for fresh generation, 'regenerate' to use existing quiz as context.",
    )
    quiz_id: UUID | None = Field(
        default=None,
        description="Required when mode='regenerate'. The existing quiz ID to use as context.",
    )
    mentor_feedback: str | None = Field(
        default=None,
        description="Optional feedback or goal for regeneration.",
    )


class QuizDeleteOut(BaseModel):
    """Returned after deleting an unpublished quiz draft."""

    quiz_id: UUID
    node_id: UUID
    deleted: bool = True


class QuizPublishRequest(BaseModel):
    """
    Body for PATCH /nodes/:id/quizzes/:quiz_id/publish.
    No body fields needed — publish is an action on the quiz identified in the path.
    Kept as an explicit schema (rather than a bare PATCH with no body) so that
    future fields (e.g., scheduled_publish_at) can be added without a route change.
    """

    pass


class QuizUnpublishRequest(BaseModel):
    """Body for PATCH /nodes/:id/quizzes/:quiz_id/unpublish."""

    retention_mode: RetentionMode = Field(
        ...,
        description=(
            "remove_completely — hidden from students, not in Previous versions. "
            "keep_for_review — archived, accessible in Previous versions."
        ),
    )


class QuizUnpublishPreviewOut(BaseModel):
    """Pre-unpublish check returned by GET unpublish-preview before committing."""

    requires_confirmation: bool
    quiz_title: str
    trainees_attempt_count: int = 0
    version_label: str | None = None


class QuizQuestionCreateRequest(BaseModel):
    """
    Body for POST /nodes/:id/quizzes/:quiz_id/questions.
    Allows mentor to manually add a question to an existing quiz.
    source is forced to 'mentor_manual' at the service layer.

    All four options (A–D) are required. correct_option must reference a
    non-empty option — validated at the service layer.

    hint_1, hint_2, hint_3 are the three progressive hints:
      hint_1: subtle nudge (1st wrong attempt)
      hint_2: narrows reasoning (2nd wrong attempt)
      hint_3: most explicit hint — does NOT reveal the answer (3rd wrong attempt)
    explanation: post-submit review only; not revealed during a live attempt.
    """

    question_text: str = Field(..., min_length=5)
    option_a: str = Field(..., min_length=1)
    option_b: str = Field(..., min_length=1)
    option_c: str = Field(..., min_length=1)
    option_d: str = Field(..., min_length=1)
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

    If any option field is provided, the merged question must still have all
    four non-empty options after the update.

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

    @model_validator(mode="after")
    def reject_blank_option_fields(self) -> Self:
        for field in ("option_a", "option_b", "option_c", "option_d"):
            value = getattr(self, field)
            if value is not None and not str(value).strip():
                raise ValueError(f"{field} must be non-empty when provided.")
        return self


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
    study_material_version_id: UUID | None
    title: str
    total_questions: int
    difficulty: QuizDifficulty
    is_published: bool
    published_at: datetime | None
    created_by: UUID
    created_at: datetime
    updated_at: datetime
    hints_status: str = "none"  # "none" | "partial" | "complete"
    questions: list[QuizQuestionOut] = Field(default_factory=list)

    # ── Quality-Check fields ──────────────────────────────────────
    qc_failed_permanently: bool = False
    qc_result: GenerationDiagnosticsOut | None = None
    next_llm_retry_at: datetime | None = None


class QuizSummaryOut(BaseModel):
    """
    Lightweight quiz row without questions. Used in list endpoints
    (GET /nodes/:id/quizzes) to show all quiz generations for the node
    without loading every question set.
    Future implementation for quiz lineage and tracking
    """

    model_config = ConfigDict(from_attributes=True)

    quiz_id: UUID
    node_id: UUID
    space_id: UUID
    study_material_version_id: UUID | None
    title: str
    total_questions: int
    difficulty: QuizDifficulty
    is_published: bool
    published_at: datetime | None
    created_at: datetime


class QuizListOut(BaseModel):
    """
    All quizzes for a node, ordered by created_at DESC (newest first).
    Future implementation for quiz lineage and tracking
    """

    node_id: UUID
    quizzes: list[QuizSummaryOut]
    total: int


class QuizHistoryItemOut(BaseModel):
    """One row in the mentor quiz history panel."""

    quiz_id: UUID
    title: str
    status_badge: str
    lifecycle_status: str
    study_material_version_id: UUID | None
    version_label: str
    total_questions: int
    difficulty: QuizDifficulty
    published_at: datetime | None = None
    can_view: bool = True
    can_delete: bool = False


class QuizMentorUiStateOut(BaseModel):
    """Mentor-facing quiz UI state resolved by the backend."""

    node_id: UUID
    resolved_quiz_id: UUID | None
    quiz_draft_exists: bool
    quiz_history: list[QuizHistoryItemOut] = Field(default_factory=list)
    published_study_material_version_id: UUID | None = None
    can_generate_quiz: bool = False
    generate_disabled_tooltip: str | None = None
    can_access_hints: bool = False
    hints_locked: bool = False
    hints_locked_tooltip: str | None = None
    can_generate_hints: bool = False
    can_regenerate_hints: bool = False
    can_publish_quiz: bool = False
    publish_disabled_tooltip: str | None = None
    can_edit_questions: bool = False
    can_regenerate_quiz: bool = False
    quiz: QuizOut | None = None
    show_update_quiz_nudge: bool = False
    quiz_sm_version_label: str | None = None
    publish_quiz_button_label: str = "Make quiz live for students"
    unpublish_quiz_button_label: str = "Remove quiz from students"
    has_other_live_quiz: bool = False
    other_live_quiz_title: str | None = None


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

    # Gated post-submit fields — populated only after attempt is submitted
    correct_option: str | None = None
    explanation: str | None = None

    # Backend-computed navigation / interaction flags
    nav_status: QuestionNavStatus = "notVisited"
    can_answer: bool = True
    can_skip: bool = True


class TraineeQuizOut(BaseModel):
    """
    Full quiz view for a trainee mid-attempt or post-submit review.
    Returned on attempt start, resume, and GET attempt.
    Correct answers and explanations are populated only after submission.
    total_correct and total_skipped are populated only after submission.
    """

    quiz_id: UUID
    node_id: UUID
    title: str
    difficulty: QuizDifficulty
    total_questions: int
    attempt_id: UUID
    attempt_status: QuizAttemptStatus
    started_at: datetime
    resume_question_id: UUID | None = None
    score_percent: int | None = None
    total_correct: int | None = None
    total_skipped: int | None = None
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

    selected_option records an answer submission. The service increments
    hint_level_reached if the answer is wrong, and sets was_locked=True once
    the answer is correct (EC-7, EC-8).

    The service validates that was_locked=False before accepting an update —
    locked questions cannot be changed.
    """

    question_id: UUID
    selected_option: CorrectOption | None = Field(
        default=None,
        description="The trainee's chosen option. Required to record an answer.",
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
    Progress fields on trainee_node_progress are updated by study_agent_service
    on submit — this response carries the raw attempt result only.
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
    next_question_id: UUID | None = None
    resume_question_id: UUID | None = None


class TraineeQuizAttemptSummaryOut(BaseModel):
    """Lightweight card for a trainee's past or in-progress attempt."""

    model_config = ConfigDict(from_attributes=True)

    attempt_id: UUID
    status: QuizAttemptStatus
    score: float | None = None
    score_percent: int | None = None
    total_correct: int | None = None
    total_skipped: int | None = None
    total_questions: int
    started_at: datetime
    submitted_at: datetime | None = None
    attempt_label: str


class TraineeQuizAttemptListOut(BaseModel):
    """All attempts for a trainee on a node's published quiz, newest first."""

    quiz_id: UUID
    node_id: UUID
    title: str
    attempts: list[TraineeQuizAttemptSummaryOut] = Field(default_factory=list)


class PublishedQuizDiscoveryOut(BaseModel):
    """
    Discovery info for a node's published quiz and active attempt.
    """

    quiz_id: UUID | None = None
    title: str | None = None
    difficulty: QuizDifficulty | None = None
    total_questions: int | None = None
    has_in_progress_attempt: bool = False
    active_attempt_id: UUID | None = None
    submitted_attempt_count: int = 0
    can_start_new_attempt: bool = True
    can_view_previous_attempts: bool = False
    is_review_only: bool = False
    review_notice: str | None = None


class TraineeArchivedQuizItemOut(BaseModel):
    """One archived quiz linked to a superseded SM version."""

    quiz_id: UUID
    study_material_version_id: UUID | None
    title: str
    difficulty: QuizDifficulty
    total_questions: int
    published_at: datetime | None
    has_trainee_attempt: bool = False
    best_score_percent: int | None = None


class TraineeArchivedQuizGroupOut(BaseModel):
    """Archived quizzes grouped under one superseded SM version."""

    study_material_version_id: UUID | None
    version_number: int
    version_label: str
    quizzes: list[TraineeArchivedQuizItemOut] = Field(default_factory=list)


class TraineeArchivedQuizListOut(BaseModel):
    """Archived quizzes for GET .../quizzes/archive."""

    node_id: UUID
    groups: list[TraineeArchivedQuizGroupOut] = Field(default_factory=list)


class ArchivedQuizReviewOut(BaseModel):
    """Read-only review of an archived quiz with answers and explanations."""

    quiz_id: UUID
    node_id: UUID
    title: str
    difficulty: QuizDifficulty
    total_questions: int
    study_material_version_id: UUID | None
    version_label: str
    is_archived_reference: bool = True
    attempt_id: UUID | None = None
    attempt_status: QuizAttemptStatus | None = None
    is_partial_attempt: bool = False
    score_percent: int | None = None
    total_correct: int | None = None
    total_skipped: int | None = None
    questions: list[TraineeQuizQuestionOut] = Field(default_factory=list)
