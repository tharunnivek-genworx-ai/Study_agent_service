# src/api/schemas/content_schemas/listing_schema.py
"""
Generic pagination primitives and typed list wrappers for the
Learning Content Service.

Mirrors the pattern from the Identity & Spaces Service's listing_endpoints.py —
PageParams as a Depends() injection, PaginatedResponse[T] as the generic
wrapper, and named typed aliases for each domain entity.

Most content endpoints don't need pagination (materials and media per node
are small sets), but quiz_attempts history and study material versions
can grow, so PaginatedResponse is wired in for those.
"""

from typing import TypeVar

from pydantic import BaseModel, Field

from src.api.schemas.quiz_schemas.quiz_schema import (
    QuizAttemptOut,
    QuizSummaryOut,
)
from src.api.schemas.study_material_schemas.study_material_schema import (
    StudyMaterialVersionSummary,
)

T = TypeVar("T")


class PageParams(BaseModel):
    """
    Reusable query-parameter schema for paginated list endpoints.
    Use as: params: PageParams = Depends() in router functions.

    Example: GET /nodes/:id/study-material/versions?page=1&limit=10
    """

    page: int = Field(default=1, ge=1, description="Page number, 1-indexed.")
    limit: int = Field(default=20, ge=1, le=100, description="Items per page, max 100.")


class PaginatedResponse[T](BaseModel):
    """
    Generic paginated wrapper for any Out schema.

    Fields:
        items  — Current page of results.
        total  — Total records matching the query (for frontend pagination UI).
        page   — Current page number.
        limit  — Page size used for this response.
        pages  — Total pages (ceil(total / limit)).
    """

    items: list[T]
    total: int
    page: int
    limit: int
    pages: int


# ── Typed List Responses ──────────────────────────────────────────────────────


class StudyMaterialVersionListResponse(PaginatedResponse[StudyMaterialVersionSummary]):
    """
    Paginated version history for a node.
    Used by GET /nodes/:id/study-material/versions.
    """

    pass


class QuizListResponse(PaginatedResponse[QuizSummaryOut]):
    """
    Paginated quiz list for a node (all generations, newest first).
    Used by GET /nodes/:id/quizzes.
    """

    pass


class QuizAttemptListResponse(PaginatedResponse[QuizAttemptOut]):
    """
    Paginated attempt history for a trainee on a specific quiz.
    Used by GET /quizzes/:quiz_id/attempts (mentor view of trainee attempts).
    """

    pass
