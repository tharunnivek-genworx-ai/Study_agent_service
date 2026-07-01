"""Unit tests for trainee archive gate helpers."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.api.core.exceptions import (
    QuizNotFoundException,
    StudyMaterialArchiveNotAvailableException,
)
from src.api.utils.content_lifecycle.archive_gates import assert_archived_quiz_access
from src.api.utils.content_lifecycle.constants import (
    LIFECYCLE_ACTIVE,
    LIFECYCLE_ARCHIVED,
)


def test_assert_archived_quiz_access_returns_archived_quiz():
    node_id = uuid4()
    quiz_id = uuid4()
    quiz = MagicMock()
    quiz.node_id = node_id
    quiz.lifecycle_status = LIFECYCLE_ARCHIVED

    session = AsyncMock()
    result = MagicMock()
    result.scalars.return_value.first.return_value = quiz
    session.execute.return_value = result

    loaded = asyncio.run(
        assert_archived_quiz_access(session, node_id=node_id, quiz_id=quiz_id)
    )
    assert loaded is quiz


def test_assert_archived_quiz_access_raises_when_missing():
    session = AsyncMock()
    result = MagicMock()
    result.scalars.return_value.first.return_value = None
    session.execute.return_value = result

    with pytest.raises(QuizNotFoundException):
        asyncio.run(
            assert_archived_quiz_access(session, node_id=uuid4(), quiz_id=uuid4())
        )


def test_assert_archived_quiz_access_raises_when_wrong_node():
    quiz = MagicMock()
    quiz.node_id = uuid4()
    quiz.lifecycle_status = LIFECYCLE_ARCHIVED

    session = AsyncMock()
    result = MagicMock()
    result.scalars.return_value.first.return_value = quiz
    session.execute.return_value = result

    with pytest.raises(QuizNotFoundException):
        asyncio.run(
            assert_archived_quiz_access(session, node_id=uuid4(), quiz_id=uuid4())
        )


def test_assert_archived_quiz_access_raises_when_not_archived():
    quiz = MagicMock()
    quiz.node_id = uuid4()
    quiz.lifecycle_status = LIFECYCLE_ACTIVE

    session = AsyncMock()
    result = MagicMock()
    result.scalars.return_value.first.return_value = quiz
    session.execute.return_value = result

    with pytest.raises(StudyMaterialArchiveNotAvailableException):
        asyncio.run(
            assert_archived_quiz_access(session, node_id=quiz.node_id, quiz_id=uuid4())
        )
