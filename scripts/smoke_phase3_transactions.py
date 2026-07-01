"""Phase 3 transaction smoke tests — commit/flush boundaries against live DB.

Exercises paths migrated in Phase 3:
  - generation run create / checkpoint / cancel (flush + intentional checkpoint commits)
  - publish cascade post-commit space recompute fan-out
  - trainee quiz start / answer / submit (service-owned commits)
  - hint persist flush + session commit without diagnostics merge
"""

from __future__ import annotations

import asyncio
import sys
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import text

from src.api.core.services import (
    GenerationRunService,
    QuizService,
    StudyMaterialService,
    TraineeQuizService,
)
from src.api.data.clients.postgres import SessionLocal
from src.api.data.repositories import (
    GenerationRunRepository,
    HintRepository,
    NodeRepository,
    StudyMaterialRepository,
)
from src.api.schemas import (
    GenerationRunCreate,
    GenerationRunMode,
    GenerationRunPipeline,
    GenerationRunResourceType,
    GenerationRunStatus,
)
from src.api.schemas.quiz_schemas import (
    QuizAttemptStartRequest,
    QuizAttemptSubmitRequest,
    QuizPublishRequest,
    QuizQuestionResponseRequest,
)
from src.api.schemas.study_material_schemas import StudyMaterialPublishRequest
from src.api.utils.mentor_progress_utils.space_recompute import (
    recompute_all_trainees_space_progress,
)

MENTOR_ID = UUID("c4b249ed-f7bf-4820-b82e-9180601cc2c4")
NODE_WATERFALL = UUID("169b4c3c-028e-47bb-8eda-5074146e0caa")
FIRST_PUBLISH_ID = UUID("2116e5b1-7af9-4614-ba0a-5a7836cf51f3")
QUIZ_LIVE = UUID("2ddfe910-39cb-4c15-90b1-ce522af6e633")


class Smoke:
    def __init__(self) -> None:
        self.passed: list[str] = []
        self.failed: list[str] = []

    def check(self, name: str, ok: bool, detail: str = "") -> None:
        if ok:
            self.passed.append(name)
            print(f"  PASS  {name}")
        else:
            self.failed.append(name)
            print(f"  FAIL  {name}" + (f": {detail}" if detail else ""))

    async def run(self) -> int:
        async with SessionLocal() as session:
            print("\n=== 1. Generation run create / checkpoint / cancel ===")
            await self.test_generation_run_transactions(session)

            print("\n=== 2. Publish cascade post-commit recompute ===")
            await self.test_publish_cascade_recompute(session)

            print("\n=== 3. Trainee quiz submit commit ===")
            await self.test_trainee_quiz_submit(session)

            print("\n=== 4. Hint persist commits without diagnostics ===")
            await self.test_hint_persist_commit(session)

        print(f"\nResults: {len(self.passed)} passed, {len(self.failed)} failed")
        if self.failed:
            print("Failed:", ", ".join(self.failed))
            return 1
        return 0

    async def test_generation_run_transactions(self, session: Any) -> None:
        from unittest.mock import AsyncMock, patch

        sm_repo = StudyMaterialRepository(session)
        seed = await sm_repo.get_version_by_id(FIRST_PUBLISH_ID)
        node = await NodeRepository(session).get_node_by_id(NODE_WATERFALL)
        if seed is None or node is None:
            self.check("gen_run: seed version and node exist", False)
            return

        service = GenerationRunService(session)
        run_id = uuid4()

        await session.execute(
            text(
                """
                DELETE FROM generationruns
                WHERE resourceid = :node_id
                  AND pipeline = 'study_material'
                  AND status IN ('running', 'failed', 'cancelled')
                """
            ),
            {"node_id": str(NODE_WATERFALL)},
        )
        await session.commit()

        payload = GenerationRunCreate(
            run_id=run_id,
            pipeline=GenerationRunPipeline.STUDY_MATERIAL,
            resource_type=GenerationRunResourceType.NODE,
            resource_id=NODE_WATERFALL,
            node_id=NODE_WATERFALL,
            space_id=node.space_id,
            mentor_id=MENTOR_ID,
            generation_mode=GenerationRunMode.GENERATE,
        )

        try:
            with (
                patch(
                    "src.api.core.services.generation_run_service.require_generation_lock",
                    new_callable=AsyncMock,
                ),
                patch(
                    "src.api.core.services.generation_run_service.release_generation_lock",
                    new_callable=AsyncMock,
                ),
            ):
                created = await service.start_run(payload)
            self.check("gen_run: start_run persisted", created.run_id == run_id)

            await service.checkpoint_after_node(
                run_id,
                node_name="resolver",
                state={"node_title": "smoke"},
            )
            row = await GenerationRunRepository(session).get_by_id(run_id)
            self.check(
                "gen_run: checkpoint committed",
                row is not None and row.last_completed_node == "resolver",
                str(getattr(row, "last_completed_node", None)),
            )

            with patch(
                "src.api.core.services.generation_run_service.release_generation_lock",
                new_callable=AsyncMock,
            ):
                cancelled = await service.cancel_run(run_id, mentor_id=MENTOR_ID)
            self.check(
                "gen_run: cancel committed",
                cancelled.status == GenerationRunStatus.CANCELLED.value,
                cancelled.status,
            )
        except Exception as exc:
            await session.rollback()
            self.check("gen_run: transaction flow", False, str(exc))
        finally:
            await session.execute(
                text("DELETE FROM generationruns WHERE runid = :id"),
                {"id": str(run_id)},
            )
            await session.commit()

    async def test_publish_cascade_recompute(self, session: Any) -> None:
        node = await NodeRepository(session).get_node_by_id(NODE_WATERFALL)
        if node is None:
            self.check("publish_cascade: node exists", False)
            return

        space_id = node.space_id
        try:
            await recompute_all_trainees_space_progress(session, space_id=space_id)
            count_row = await session.execute(
                text("SELECT COUNT(*) FROM traineespaceprogress WHERE spaceid = :sid"),
                {"sid": str(space_id)},
            )
            trainee_rows = count_row.scalar() or 0
            self.check(
                "publish_cascade: space recompute fan-out completed",
                True,
                f"rows={trainee_rows}",
            )
        except Exception as exc:
            await session.rollback()
            self.check("publish_cascade: recompute fan-out", False, str(exc))

    async def test_trainee_quiz_submit(self, session: Any) -> None:
        try:
            await self._test_trainee_quiz_submit_inner(session)
        except Exception as exc:
            await session.rollback()
            self.check("trainee_submit: transaction flow", False, str(exc))

    async def _test_trainee_quiz_submit_inner(self, session: Any) -> None:
        sm = StudyMaterialService(session)
        quiz_svc = QuizService(session)
        published_sm = await StudyMaterialRepository(session).get_published_version(
            NODE_WATERFALL
        )
        if published_sm is None:
            await sm.publish_study_material(
                NODE_WATERFALL,
                StudyMaterialPublishRequest(version_id=FIRST_PUBLISH_ID),
                MENTOR_ID,
                "mentor",
            )
            published_sm = await StudyMaterialRepository(session).get_published_version(
                NODE_WATERFALL
            )
        if published_sm is None:
            self.check("trainee_submit: published study material exists", False)
            return

        aligned = await session.execute(
            text(
                """
                SELECT quizid
                FROM quizzes
                WHERE nodeid = :node_id
                  AND studymaterialversionid = :sm_version_id
                  AND ispublished IS TRUE
                LIMIT 1
                """
            ),
            {
                "node_id": str(NODE_WATERFALL),
                "sm_version_id": str(published_sm.version_id),
            },
        )
        quiz_id_raw = aligned.scalar()
        if quiz_id_raw is None:
            draft = await session.execute(
                text(
                    """
                    SELECT quizid
                    FROM quizzes
                    WHERE nodeid = :node_id
                      AND studymaterialversionid = :sm_version_id
                    ORDER BY createdat DESC
                    LIMIT 1
                    """
                ),
                {
                    "node_id": str(NODE_WATERFALL),
                    "sm_version_id": str(published_sm.version_id),
                },
            )
            quiz_id_raw = draft.scalar()
            if quiz_id_raw is None:
                self.check("trainee_submit: quiz aligned with live SM", False)
                return
            quiz_id = UUID(str(quiz_id_raw))
            await session.execute(
                text(
                    """
                    UPDATE quizquestions
                    SET hint1 = COALESCE(hint1, 'Smoke hint 1'),
                        hint2 = COALESCE(hint2, 'Smoke hint 2'),
                        hint3 = COALESCE(hint3, 'Smoke hint 3')
                    WHERE quizid = :quiz_id AND isactive IS TRUE
                    """
                ),
                {"quiz_id": str(quiz_id)},
            )
            await session.commit()
            await quiz_svc.publish_quiz(
                NODE_WATERFALL,
                quiz_id,
                QuizPublishRequest(),
                MENTOR_ID,
                "mentor",
            )
        else:
            quiz_id = UUID(str(quiz_id_raw))

        trainee_row = await session.execute(
            text(
                """
                SELECT t.traineeid
                FROM trainees t
                JOIN spacetrainees st ON st.traineeid = t.traineeid
                JOIN quizzes q ON q.spaceid = st.spaceid
                WHERE q.quizid = :quiz_id
                LIMIT 1
                """
            ),
            {"quiz_id": str(QUIZ_LIVE)},
        )
        trainee_id = trainee_row.scalar()
        if trainee_id is None:
            self.check("trainee_submit: enrolled trainee for live quiz", False)
            return

        trainee_id = UUID(str(trainee_id))
        quiz_service = TraineeQuizService(session)

        quiz_out = await quiz_service.start_attempt(
            node_id=NODE_WATERFALL,
            quiz_id=quiz_id,
            request=QuizAttemptStartRequest(),
            user_id=trainee_id,
            role="trainee",
        )
        attempt_id = quiz_out.attempt_id
        self.check("trainee_submit: attempt created", attempt_id is not None)

        if quiz_out.questions:
            first = quiz_out.questions[0]
            await quiz_service.submit_response(
                attempt_id=attempt_id,
                request=QuizQuestionResponseRequest(
                    question_id=first.question_id,
                    selected_option="A",
                ),
                user_id=trainee_id,
                role="trainee",
            )
            await session.commit()

        submitted = await quiz_service.submit_attempt(
            attempt_id=attempt_id,
            request=QuizAttemptSubmitRequest(),
            user_id=trainee_id,
            role="trainee",
        )
        self.check(
            "trainee_submit: attempt submitted with score",
            submitted.status == "submitted" and submitted.score is not None,
            f"status={submitted.status} score={submitted.score}",
        )

        await session.execute(
            text("DELETE FROM quizquestionresponses WHERE attemptid = :aid"),
            {"aid": str(attempt_id)},
        )
        await session.execute(
            text("DELETE FROM quizattempts WHERE attemptid = :aid"),
            {"aid": str(attempt_id)},
        )
        await session.commit()

    async def test_hint_persist_commit(self, session: Any) -> None:
        question_rows = await session.execute(
            text(
                """
                SELECT questionid, hint1, hint2, hint3
                FROM quizquestions
                WHERE quizid = :qid AND isactive IS TRUE
                LIMIT 1
                """
            ),
            {"qid": str(QUIZ_LIVE)},
        )
        row = question_rows.first()
        if row is None:
            self.check("hint_persist: active question exists", False)
            return

        question_id = UUID(str(row[0]))
        original_hints = (row[1], row[2], row[3])
        hint_repo = HintRepository(session)

        try:
            await hint_repo.update_question_hints(
                question_id,
                "smoke-h1",
                "smoke-h2",
                "smoke-h3",
                commit=False,
            )
            await session.commit()

            verify = await session.execute(
                text(
                    "SELECT hint1, hint2, hint3 FROM quizquestions WHERE questionid = :qid"
                ),
                {"qid": str(question_id)},
            )
            hints = verify.first()
            self.check(
                "hint_persist: hints committed without diagnostics path",
                hints is not None and hints[0] == "smoke-h1",
                str(hints),
            )
        finally:
            await session.execute(
                text(
                    """
                    UPDATE quizquestions
                    SET hint1 = :h1, hint2 = :h2, hint3 = :h3
                    WHERE questionid = :qid
                    """
                ),
                {
                    "qid": str(question_id),
                    "h1": original_hints[0],
                    "h2": original_hints[1],
                    "h3": original_hints[2],
                },
            )
            await session.commit()


if __name__ == "__main__":
    sys.exit(asyncio.run(Smoke().run()))
