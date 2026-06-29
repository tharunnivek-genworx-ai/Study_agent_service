# src/api/rest/routes/quiz_route.py
"""
Routes for quizzes, quiz_questions, quiz_attempts, and quiz_question_responses.

Quiz lifecycle (TDD §3.2.2 and §3.2.3):
  MENTOR — Quiz questions (Quiz Agent LangGraph):
    Generate        → POST   /nodes/{node_id}/quizzes/generate      (LLM placeholder)
    List quizzes    → GET    /nodes/{node_id}/quizzes
    Get quiz        → GET    /nodes/{node_id}/quizzes/{quiz_id}
    Publish quiz    → PATCH  /nodes/{node_id}/quizzes/{quiz_id}/publish
    Add question    → POST   /nodes/{node_id}/quizzes/{quiz_id}/questions
    Update question → PATCH  /nodes/{node_id}/quizzes/{quiz_id}/questions/{question_id}
    Reorder qs      → PATCH  /nodes/{node_id}/quizzes/{quiz_id}/questions/reorder
    Delete question → DELETE /nodes/{node_id}/quizzes/{quiz_id}/questions/{question_id}

  MENTOR — Hints (Hint Agent LangGraph, separate flow):
    Generate hints    → POST /nodes/{node_id}/quizzes/{quiz_id}/hints/generate
    Regenerate hints  → POST /nodes/{node_id}/quizzes/{quiz_id}/hints/regenerate

  TRAINEE:
    Start attempt   → POST   /nodes/{node_id}/quizzes/{quiz_id}/attempt
    Submit response → POST   /attempts/{attempt_id}/response
    Submit attempt  → POST   /attempts/{attempt_id}/submit
    Get attempt     → GET    /attempts/{attempt_id}
"""

from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.core.services import QuizService
from src.api.data.clients.postgres import get_db
from src.api.rest.routes.dependencies import get_current_user
from src.api.schemas.identity_schemas import TokenPayload
from src.api.schemas.quiz_schemas import (
    QuizDeleteOut,
    QuizGenerateRequest,
    QuizMentorUiStateOut,
    QuizOut,
    QuizPublishRequest,
    QuizQuestionCreateRequest,
    QuizQuestionDeletedOut,
    QuizQuestionOut,
    QuizQuestionReorderRequest,
    QuizQuestionUpdateRequest,
    QuizUnpublishPreviewOut,
    QuizUnpublishRequest,
)

router = APIRouter(tags=["Quiz"])


# ── Mentor: Quiz Generation & Management ─────────────────────────────────────


@router.post(
    "/nodes/{node_id}/quizzes/generate",
    status_code=status.HTTP_201_CREATED,
    response_model=QuizOut,
)
async def generate_quiz(
    node_id: UUID,
    payload: QuizGenerateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: TokenPayload = Depends(get_current_user),
) -> QuizOut:
    """Mentor triggers quiz question generation from a published study material version.

    Creates quiz and question rows without hints. After finalizing the draft,
    call the separate hint generation endpoint (Hint Agent LangGraph flow).
    Returns the created QuizOut with all questions.
    """
    service = QuizService(db)
    return await service.generate_quiz(
        node_id, payload, current_user.sub, current_user.role
    )


@router.get(
    "/nodes/{node_id}/quizzes/mentor-ui-state",
    response_model=QuizMentorUiStateOut,
)
async def get_quiz_mentor_ui_state(
    node_id: UUID,
    preferred_quiz_id: UUID | None = Query(default=None),
    include_quiz: bool = Query(default=False),
    db: AsyncSession = Depends(get_db),
    current_user: TokenPayload = Depends(get_current_user),
) -> QuizMentorUiStateOut:
    """Mentor UI flags: resolved quiz id, draft existence, and optional full quiz."""
    service = QuizService(db)
    return await service.get_mentor_quiz_ui_state(
        node_id,
        current_user.sub,
        current_user.role,
        preferred_quiz_id=preferred_quiz_id,
        include_quiz=include_quiz,
    )


@router.get("/nodes/{node_id}/quizzes/{quiz_id}", response_model=QuizOut)
async def get_quiz(
    node_id: UUID,
    quiz_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: TokenPayload = Depends(get_current_user),
) -> QuizOut:
    """Mentor fetches a single quiz with all its questions."""
    service = QuizService(db)
    return await service.get_quiz(node_id, quiz_id, current_user.sub, current_user.role)


@router.patch(
    "/nodes/{node_id}/quizzes/{quiz_id}/publish",
    response_model=QuizOut,
)
async def publish_quiz(
    node_id: UUID,
    quiz_id: UUID,
    payload: QuizPublishRequest,
    db: AsyncSession = Depends(get_db),
    current_user: TokenPayload = Depends(get_current_user),
) -> QuizOut:
    """Mentor publishes a quiz, making it visible to trainees (is_published=True)."""
    service = QuizService(db)
    return await service.publish_quiz(
        node_id, quiz_id, payload, current_user.sub, current_user.role
    )


@router.get(
    "/nodes/{node_id}/quizzes/{quiz_id}/unpublish-preview",
    response_model=QuizUnpublishPreviewOut,
)
async def preview_unpublish_quiz(
    node_id: UUID,
    quiz_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: TokenPayload = Depends(get_current_user),
) -> QuizUnpublishPreviewOut:
    """Pre-unpublish check: returns attempt counts and confirmation flag without writing."""
    service = QuizService(db)
    return await service.preview_unpublish_quiz(
        node_id, quiz_id, current_user.sub, current_user.role
    )


@router.patch(
    "/nodes/{node_id}/quizzes/{quiz_id}/unpublish",
    response_model=QuizOut,
)
async def unpublish_quiz(
    node_id: UUID,
    quiz_id: UUID,
    payload: QuizUnpublishRequest,
    db: AsyncSession = Depends(get_db),
    current_user: TokenPayload = Depends(get_current_user),
) -> QuizOut:
    """Mentor unpublishes a quiz with a retention choice (remove or keep for review)."""
    service = QuizService(db)
    return await service.unpublish_quiz(
        node_id, quiz_id, payload, current_user.sub, current_user.role
    )


# ── Mentor: Question Management ───────────────────────────────────────────────


@router.delete(
    "/nodes/{node_id}/quizzes/{quiz_id}",
    response_model=QuizDeleteOut,
)
async def delete_quiz(
    node_id: UUID,
    quiz_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: TokenPayload = Depends(get_current_user),
) -> QuizDeleteOut:
    """Soft-discard an unpublished quiz draft from the mentor workspace.

    Live quizzes and quizzes kept in Previous versions for students cannot be
    discarded via this endpoint.
    """
    service = QuizService(db)
    return await service.delete_quiz(
        node_id, quiz_id, current_user.sub, current_user.role
    )


# ── Mentor: Question Management ───────────────────────────────────────────────


@router.post(
    "/nodes/{node_id}/quizzes/{quiz_id}/questions",
    response_model=QuizQuestionOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_quiz_question(
    node_id: UUID,
    quiz_id: UUID,
    payload: QuizQuestionCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: TokenPayload = Depends(get_current_user),
) -> QuizQuestionOut:
    """Mentor manually adds a question to an existing quiz.

    source is forced to 'mentor_manual' at the service layer.
    correct_option must reference a non-None option (validated in service).
    """
    service = QuizService(db)
    return await service.create_question(
        node_id, quiz_id, payload, current_user.sub, current_user.role
    )


@router.patch(
    "/nodes/{node_id}/quizzes/{quiz_id}/questions/reorder",
    status_code=status.HTTP_200_OK,
)
async def reorder_quiz_questions(
    node_id: UUID,
    quiz_id: UUID,
    payload: QuizQuestionReorderRequest,
    db: AsyncSession = Depends(get_db),
    current_user: TokenPayload = Depends(get_current_user),
) -> dict[str, object]:
    """Bulk-update order_index for all active questions in a quiz.

    question_ids must be the complete active set — partial reorders are rejected.
    Registered before /questions/{question_id} so "reorder" is not parsed as a UUID.
    """
    service = QuizService(db)
    return await service.reorder_questions(
        node_id, quiz_id, payload, current_user.sub, current_user.role
    )


@router.patch(
    "/nodes/{node_id}/quizzes/{quiz_id}/questions/{question_id}",
    response_model=QuizQuestionOut,
)
async def update_quiz_question(
    node_id: UUID,
    quiz_id: UUID,
    question_id: UUID,
    payload: QuizQuestionUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: TokenPayload = Depends(get_current_user),
) -> QuizQuestionOut:
    """Mentor partially updates a question."""
    service = QuizService(db)
    return await service.update_question(
        node_id, quiz_id, question_id, payload, current_user.sub, current_user.role
    )


@router.delete(
    "/nodes/{node_id}/quizzes/{quiz_id}/questions/{question_id}",
    response_model=QuizQuestionDeletedOut,
)
async def delete_quiz_question(
    node_id: UUID,
    quiz_id: UUID,
    question_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: TokenPayload = Depends(get_current_user),
) -> QuizQuestionDeletedOut:
    """Mentor soft-deletes a question (is_active=False).

    Historical attempt responses for this question are preserved and rendered
    with '(Removed)' by the frontend (EC-10).
    """
    service = QuizService(db)
    return await service.delete_question(
        node_id, quiz_id, question_id, current_user.sub, current_user.role
    )
