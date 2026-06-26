"""Smoke-test mentor content visibility flows via StudyMaterialService / QuizService."""

from __future__ import annotations

import asyncio
import sys
from uuid import UUID

from src.api.core.services.quiz_services.quiz_service import QuizService
from src.api.core.services.study_agent_services.study_material_service import (
    StudyMaterialService,
)
from src.api.data.clients.postgres.database import SessionLocal
from src.api.schemas.quiz_schemas.quiz_schema import (
    QuizPublishRequest,
    QuizUnpublishRequest,
)
from src.api.schemas.study_material_schemas.study_material_schema import (
    RetentionMode,
    StudyMaterialActivateRequest,
    StudyMaterialManualEditRequest,
    StudyMaterialPublishRequest,
    StudyMaterialUnpublishRequest,
)

# IDs from the current capstone_db seed (SDLC + useState nodes).
MENTOR_ID = UUID("c4b249ed-f7bf-4820-b82e-9180601cc2c4")
ROLE = "mentor"

NODE_WATERFALL = UUID("169b4c3c-028e-47bb-8eda-5074146e0caa")  # SDLC
V2 = UUID("147770d1-8406-455a-9c13-acfd36c3cdc5")  # useState SM v2 draft (shelf test)
FIRST_PUBLISH_ID = UUID("2116e5b1-7af9-4614-ba0a-5a7836cf51f3")  # SM v4
FIRST_PUBLISH_VERSION = 4

NODE_USESTATE = UUID("fb0a743b-1b64-4a93-b89e-1139d6c94568")  # useState()
QUIZ_LIVE_USESTATE = UUID("4638fc5a-6862-4e2e-9a43-fbea12184fd8")

NODE_QUIZ = UUID("169b4c3c-028e-47bb-8eda-5074146e0caa")  # SDLC quiz flows
QUIZ_LIVE = UUID("2ddfe910-39cb-4c15-90b1-ce522af6e633")
QUIZ_DRAFT = UUID("6531f5a8-3fb5-4fb6-b9e7-4209a23d9baf")


def version_in_label(label: str, number: int) -> bool:
    return f"v{number}" in label


class SmokeTest:
    def __init__(self) -> None:
        self.passed: list[str] = []
        self.failed: list[str] = []

    def check(self, name: str, condition: bool, detail: str = "") -> None:
        if condition:
            self.passed.append(name)
            print(f"  PASS  {name}")
        else:
            self.failed.append(name)
            print(f"  FAIL  {name}" + (f": {detail}" if detail else ""))

    async def run(self) -> int:
        async with SessionLocal() as session:
            sm = StudyMaterialService(session)
            quiz = QuizService(session)

            print("\n=== 0. Prepare SDLC node ===")
            await self.prepare_sdlc_node(sm)

            print("\n=== 1. First publish (SDLC) — S1 ===")
            await self.test_first_publish(sm)

            print("\n=== 2. Replace live version (Waterfall) — S2/S8 ===")
            v4_id = await self.test_replace_live(sm)

            print("\n=== 3. Unpublish live (Waterfall) — S3/S4 ===")
            await self.test_unpublish(sm, v4_id)

            print("\n=== 4. Move draft to shelf (Waterfall) ===")
            await self.test_shelf(sm)

            print("\n=== 5. SM supersede preserves live quiz (usestate) — S2 ===")
            await self.test_sm_supersede_preserves_quiz(sm, quiz)

            print("\n=== 6. Quiz replace + unpublish (SDLC) — S5/S6/S7 ===")
            await self.prepare_quiz_node(sm)
            await self.test_quiz_flows(quiz)

            print("\n=== Cleanup: restore Waterfall to unpublished ===")
            await self.cleanup_waterfall(sm)

        print(f"\nResults: {len(self.passed)} passed, {len(self.failed)} failed")
        if self.failed:
            print("Failed:", ", ".join(self.failed))
            return 1
        return 0

    async def prepare_sdlc_node(self, sm: StudyMaterialService) -> None:
        """Unpublish any live SM on SDLC and activate the draft used for first-publish."""
        history = await sm.list_versions(
            NODE_WATERFALL, MENTOR_ID, ROLE, archived=False
        )
        for version in history.versions:
            if version.is_published:
                await sm.unpublish_study_material(
                    NODE_WATERFALL,
                    StudyMaterialUnpublishRequest(
                        version_id=version.version_id,
                        retention_mode=RetentionMode.remove_completely,
                    ),
                    MENTOR_ID,
                    ROLE,
                )
        await sm.activate_study_material(
            NODE_WATERFALL,
            StudyMaterialActivateRequest(version_id=FIRST_PUBLISH_ID),
            MENTOR_ID,
            ROLE,
        )
        self.check("prepare: activated first-publish draft", True)

    async def prepare_quiz_node(self, sm: StudyMaterialService) -> None:
        """Ensure SDLC has live study material so quiz publish is allowed."""
        await sm.publish_study_material(
            NODE_QUIZ,
            StudyMaterialPublishRequest(version_id=FIRST_PUBLISH_ID),
            MENTOR_ID,
            ROLE,
        )
        self.check("prepare_quiz: live study material on SDLC", True)

    async def test_first_publish(self, sm: StudyMaterialService) -> None:
        state = await sm.get_mentor_ui_state(NODE_WATERFALL, MENTOR_ID, ROLE)
        actions = state.displayed_version_actions
        vis = state.student_visibility

        self.check(
            "first_publish: button label",
            actions.publish_button_label == "Make live for students",
            actions.publish_button_label,
        )
        self.check(
            "first_publish: no live material in banner",
            vis.live_material_label is None,
            str(vis),
        )

        preview = await sm.preview_publish_study_material(
            NODE_WATERFALL, FIRST_PUBLISH_ID, MENTOR_ID, ROLE
        )
        self.check(
            "first_publish: preview no replace confirm gate",
            preview.requires_confirmation is False,
            preview.model_dump_json(),
        )
        self.check(
            "first_publish: not replacing live",
            preview.is_replacing_live_version is False,
            preview.model_dump_json(),
        )

        published = await sm.publish_study_material(
            NODE_WATERFALL,
            StudyMaterialPublishRequest(version_id=FIRST_PUBLISH_ID),
            MENTOR_ID,
            ROLE,
        )
        self.check("first_publish: publish succeeds", published.is_published is True)

        state = await sm.get_mentor_ui_state(NODE_WATERFALL, MENTOR_ID, ROLE)
        vis = state.student_visibility
        self.check(
            "first_publish: banner shows live version",
            vis.live_material_label is not None
            and version_in_label(vis.live_material_label, FIRST_PUBLISH_VERSION),
            str(vis),
        )

        history = await sm.list_versions(
            NODE_WATERFALL, MENTOR_ID, ROLE, archived=False
        )
        published_row = next(
            v for v in history.versions if v.version_id == FIRST_PUBLISH_ID
        )
        self.check(
            "first_publish: badge Live for students",
            published_row.mentor_display_badge == "Live for students",
            published_row.mentor_display_badge,
        )

    async def test_replace_live(self, sm: StudyMaterialService) -> UUID:
        active = await sm.get_active_version(NODE_WATERFALL, MENTOR_ID, ROLE)
        assert active is not None
        v4 = await sm.manual_edit_study_material(
            NODE_WATERFALL,
            StudyMaterialManualEditRequest(
                content=(active.content or "") + "\n\n<!-- smoke v4 -->"
            ),
            MENTOR_ID,
            ROLE,
        )
        v4_id = v4.version_id
        new_version_number = v4.version_number

        state = await sm.get_mentor_ui_state(NODE_WATERFALL, MENTOR_ID, ROLE)
        self.check(
            "replace_live: button label",
            state.displayed_version_actions.publish_button_label
            == "Replace live version",
            state.displayed_version_actions.publish_button_label,
        )

        preview = await sm.preview_publish_study_material(
            NODE_WATERFALL, v4_id, MENTOR_ID, ROLE
        )
        self.check(
            "replace_live: requires_confirmation", preview.requires_confirmation is True
        )
        self.check(
            "replace_live: is_replacing_live_version",
            preview.is_replacing_live_version is True,
        )
        self.check(
            "replace_live: previous_version_label set",
            preview.previous_version_label is not None
            and version_in_label(preview.previous_version_label, FIRST_PUBLISH_VERSION),
            preview.previous_version_label,
        )

        await sm.publish_study_material(
            NODE_WATERFALL,
            StudyMaterialPublishRequest(version_id=v4_id),
            MENTOR_ID,
            ROLE,
        )

        state = await sm.get_mentor_ui_state(NODE_WATERFALL, MENTOR_ID, ROLE)
        vis = state.student_visibility
        self.check(
            "replace_live: banner shows new live version",
            vis.live_material_label is not None
            and version_in_label(vis.live_material_label, new_version_number),
            str(vis),
        )
        self.check(
            "replace_live: previous versions count >= 1",
            vis.previous_version_count >= 1,
        )
        self.check(
            "replace_live: prior live version in previous labels",
            any(
                version_in_label(label, FIRST_PUBLISH_VERSION)
                for label in vis.previous_version_labels
            ),
            str(vis.previous_version_labels),
        )

        history = await sm.list_versions(
            NODE_WATERFALL, MENTOR_ID, ROLE, archived=False
        )
        prior_row = next(
            v for v in history.versions if v.version_id == FIRST_PUBLISH_ID
        )
        self.check(
            "replace_live: prior live badge Previous for students",
            prior_row.mentor_display_badge == "Previous for students",
            prior_row.mentor_display_badge,
        )

        return v4_id

    async def test_unpublish(
        self, sm: StudyMaterialService, live_version_id: UUID
    ) -> None:
        unpublish_preview = await sm.preview_unpublish_study_material(
            NODE_WATERFALL, live_version_id, MENTOR_ID, ROLE
        )
        self.check(
            "unpublish: preview requires_confirmation",
            unpublish_preview.requires_confirmation is True,
            unpublish_preview.model_dump_json(),
        )
        self.check(
            "unpublish: engagement counts present",
            unpublish_preview.trainees_read_count >= 0
            and unpublish_preview.trainees_quiz_attempt_count >= 0,
            unpublish_preview.model_dump_json(),
        )

        state_before = await sm.get_mentor_ui_state(NODE_WATERFALL, MENTOR_ID, ROLE)
        self.check(
            "unpublish: button label",
            state_before.displayed_version_actions.unpublish_button_label
            == "Remove from students",
            state_before.displayed_version_actions.unpublish_button_label,
        )

        await sm.unpublish_study_material(
            NODE_WATERFALL,
            StudyMaterialUnpublishRequest(
                version_id=live_version_id,
                retention_mode=RetentionMode.remove_completely,
            ),
            MENTOR_ID,
            ROLE,
        )

        state = await sm.get_mentor_ui_state(NODE_WATERFALL, MENTOR_ID, ROLE)
        self.check(
            "unpublish: banner shows nothing live",
            state.student_visibility.live_material_label is None,
            str(state.student_visibility),
        )

        history = await sm.list_versions(
            NODE_WATERFALL, MENTOR_ID, ROLE, archived=False
        )
        v4_row = next(v for v in history.versions if v.version_id == live_version_id)
        self.check(
            "unpublish: badge Removed from students",
            v4_row.mentor_display_badge == "Removed from students",
            v4_row.mentor_display_badge,
        )

    async def test_shelf(self, sm: StudyMaterialService) -> None:
        from sqlalchemy import text

        shelf_node = NODE_USESTATE
        session = sm.session
        await session.execute(
            text("UPDATE topicnodes SET isactive = true WHERE nodeid = :node_id"),
            {"node_id": shelf_node},
        )
        await session.commit()

        vis_before = (
            await sm.get_mentor_ui_state(shelf_node, MENTOR_ID, ROLE)
        ).student_visibility

        await sm.archive_study_material_version(shelf_node, V2, MENTOR_ID, ROLE)

        vis_after = (
            await sm.get_mentor_ui_state(shelf_node, MENTOR_ID, ROLE)
        ).student_visibility
        self.check(
            "shelf: student banner unchanged",
            vis_before.live_material_label == vis_after.live_material_label,
        )

        archived = await sm.list_versions(shelf_node, MENTOR_ID, ROLE, archived=True)
        v2_row = next(v for v in archived.versions if v.version_id == V2)
        self.check(
            "archive: In your archive badge",
            v2_row.mentor_display_badge == "In your archive",
            v2_row.mentor_display_badge,
        )

        await sm.unarchive_study_material_version(shelf_node, V2, MENTOR_ID, ROLE)

    async def test_sm_supersede_preserves_quiz(
        self, sm: StudyMaterialService, quiz: QuizService
    ) -> None:
        from sqlalchemy import text

        session = sm.session
        await session.execute(
            text("UPDATE topicnodes SET isactive = true WHERE nodeid = :node_id"),
            {"node_id": NODE_USESTATE},
        )
        await session.commit()

        before = await quiz.get_mentor_quiz_ui_state(
            NODE_USESTATE,
            MENTOR_ID,
            ROLE,
            preferred_quiz_id=QUIZ_LIVE_USESTATE,
            include_quiz=True,
        )
        self.check(
            "supersede: live quiz exists before SM replace",
            before.quiz is not None and before.quiz.is_published is True,
            str(getattr(before.quiz, "is_published", None)),
        )
        if before.quiz is None:
            return

        before_quiz_id = before.quiz.quiz_id
        before_title = before.quiz.title

        await sm.activate_study_material(
            NODE_USESTATE,
            StudyMaterialActivateRequest(version_id=V2),
            MENTOR_ID,
            ROLE,
        )
        active = await sm.get_active_version(NODE_USESTATE, MENTOR_ID, ROLE)
        if active is None:
            self.check(
                "supersede: active SM version exists", False, "no active version"
            )
            return

        new_sm = await sm.manual_edit_study_material(
            NODE_USESTATE,
            StudyMaterialManualEditRequest(
                content=(active.content or "") + "\n\n<!-- smoke supersede -->"
            ),
            MENTOR_ID,
            ROLE,
        )

        preview = await sm.preview_publish_study_material(
            NODE_USESTATE, new_sm.version_id, MENTOR_ID, ROLE
        )
        self.check(
            "supersede: SM replace preview has no quiz side effects",
            not hasattr(preview, "will_pause_draft_count"),
            preview.model_dump_json(),
        )

        await sm.publish_study_material(
            NODE_USESTATE,
            StudyMaterialPublishRequest(version_id=new_sm.version_id),
            MENTOR_ID,
            ROLE,
        )

        after = await quiz.get_mentor_quiz_ui_state(
            NODE_USESTATE,
            MENTOR_ID,
            ROLE,
            preferred_quiz_id=QUIZ_LIVE_USESTATE,
            include_quiz=True,
        )
        self.check(
            "supersede: quiz still published after SM replace",
            after.quiz is not None and after.quiz.is_published is True,
            str(getattr(after.quiz, "is_published", None)),
        )
        self.check(
            "supersede: same quiz id after SM replace",
            after.quiz is not None and after.quiz.quiz_id == before_quiz_id,
            f"before={before_quiz_id} after={getattr(after.quiz, 'quiz_id', None)}",
        )
        self.check(
            "supersede: quiz title unchanged",
            after.quiz is not None and after.quiz.title == before_title,
            f"before={before_title} after={getattr(after.quiz, 'title', None)}",
        )
        self.check(
            "supersede: optional update nudge only (non-blocking)",
            hasattr(after, "show_update_quiz_nudge"),
            "show_update_quiz_nudge missing from mentor UI state",
        )

    async def test_quiz_flows(self, quiz: QuizService) -> None:
        await self._test_quiz_flows_inner(quiz)

    async def _test_quiz_flows_inner(self, quiz: QuizService) -> None:
        from sqlalchemy import text

        session = quiz.session
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
            {"quiz_id": QUIZ_DRAFT},
        )
        await session.commit()

        live_state = await quiz.get_mentor_quiz_ui_state(
            NODE_QUIZ, MENTOR_ID, ROLE, preferred_quiz_id=QUIZ_LIVE, include_quiz=True
        )
        self.check(
            "quiz: live unpublish label",
            live_state.unpublish_quiz_button_label == "Remove quiz from students",
            live_state.unpublish_quiz_button_label,
        )
        self.check(
            "quiz: live quiz is published",
            live_state.quiz is not None and live_state.quiz.is_published is True,
            str(getattr(live_state.quiz, "is_published", None)),
        )
        self.check(
            "quiz: no stale-version fields on mentor UI state",
            not hasattr(live_state, "is_stale_version"),
            "is_stale_version should be removed",
        )

        draft_state = await quiz.get_mentor_quiz_ui_state(
            NODE_QUIZ, MENTOR_ID, ROLE, preferred_quiz_id=QUIZ_DRAFT, include_quiz=True
        )
        self.check(
            "quiz: draft has_other_live_quiz", draft_state.has_other_live_quiz is True
        )
        self.check(
            "quiz: replace publish label",
            draft_state.publish_quiz_button_label == "Replace live quiz",
            draft_state.publish_quiz_button_label,
        )
        self.check(
            "quiz: other live quiz title present",
            draft_state.other_live_quiz_title is not None,
            str(draft_state.other_live_quiz_title),
        )
        self.check(
            "quiz replace: can_publish_quiz after hint setup",
            draft_state.can_publish_quiz is True,
            draft_state.publish_disabled_tooltip or "cannot publish",
        )

        unpublish_preview = await quiz.preview_unpublish_quiz(
            NODE_QUIZ, QUIZ_LIVE, MENTOR_ID, ROLE
        )
        self.check(
            "quiz unpublish preview: requires_confirmation",
            unpublish_preview.requires_confirmation is True,
            unpublish_preview.model_dump_json(),
        )
        self.check(
            "quiz unpublish preview: attempt count present",
            unpublish_preview.trainees_attempt_count >= 0,
            unpublish_preview.model_dump_json(),
        )

        if draft_state.can_publish_quiz:
            published_draft = await quiz.publish_quiz(
                NODE_QUIZ,
                QUIZ_DRAFT,
                QuizPublishRequest(),
                MENTOR_ID,
                ROLE,
            )
            self.check(
                "quiz replace: publish draft succeeds",
                published_draft.is_published is True,
            )

            after = await quiz.get_mentor_quiz_ui_state(
                NODE_QUIZ,
                MENTOR_ID,
                ROLE,
                preferred_quiz_id=QUIZ_DRAFT,
                include_quiz=True,
            )
            self.check(
                "quiz replace: draft now live",
                after.quiz is not None and after.quiz.is_published is True,
            )
            self.check(
                "quiz replace: no other live quiz flag after replace",
                after.has_other_live_quiz is False,
            )

            await quiz.unpublish_quiz(
                NODE_QUIZ,
                QUIZ_DRAFT,
                QuizUnpublishRequest(retention_mode=RetentionMode.remove_completely),
                MENTOR_ID,
                ROLE,
            )
            restored = await quiz.get_mentor_quiz_ui_state(
                NODE_QUIZ,
                MENTOR_ID,
                ROLE,
                preferred_quiz_id=QUIZ_DRAFT,
                include_quiz=True,
            )
            self.check(
                "quiz unpublish remove: draft no longer live",
                restored.quiz is not None and restored.quiz.is_published is False,
            )

            await quiz.publish_quiz(
                NODE_QUIZ,
                QUIZ_LIVE,
                QuizPublishRequest(),
                MENTOR_ID,
                ROLE,
            )
            restored_live = await quiz.get_mentor_quiz_ui_state(
                NODE_QUIZ,
                MENTOR_ID,
                ROLE,
                preferred_quiz_id=QUIZ_LIVE,
                include_quiz=True,
            )
            self.check(
                "quiz cleanup: original live quiz restored",
                restored_live.quiz is not None
                and restored_live.quiz.is_published is True,
                str(getattr(restored_live.quiz, "is_published", None)),
            )

    async def cleanup_waterfall(self, sm: StudyMaterialService) -> None:
        history = await sm.list_versions(
            NODE_WATERFALL, MENTOR_ID, ROLE, archived=False
        )
        for v in history.versions:
            if v.is_published:
                try:
                    await sm.unpublish_study_material(
                        NODE_WATERFALL,
                        StudyMaterialUnpublishRequest(
                            version_id=v.version_id,
                            retention_mode=RetentionMode.remove_completely,
                        ),
                        MENTOR_ID,
                        ROLE,
                    )
                except Exception:
                    pass
        try:
            await sm.activate_study_material(
                NODE_WATERFALL,
                StudyMaterialActivateRequest(version_id=FIRST_PUBLISH_ID),
                MENTOR_ID,
                ROLE,
            )
        except Exception:
            pass


if __name__ == "__main__":
    sys.exit(asyncio.run(SmokeTest().run()))
