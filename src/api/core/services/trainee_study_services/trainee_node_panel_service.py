"""
Service for trainee topic detail panel aggregation (Option 1 orchestrator).

``get_node_panel`` loads tree/content from the study repository layer and
fetches progress snapshots from ``TraineeProgressService`` — it never reads
progress tables directly.
"""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.api.core.services.progress_services.trainee_progress_service import (
    TraineeProgressService,
)
from src.api.core.services.trainee_quiz_services.trainee_quiz_service import (
    TraineeQuizService,
)
from src.api.data.models.postgres.e_spaces_trees.topic_nodes import TopicNode
from src.api.data.repositories.trainee_study_repositories.trainee_node_panel_repository import (
    TraineeNodePanelRepository,
)
from src.api.schemas.progress_schemas.trainee_progress_schema import (
    TraineeNodeProgressBatchItemOut,
)
from src.api.schemas.study_material_schemas.trainee_node_panel_schema import (
    BreadcrumbItemOut,
    NavSuggestionOut,
    OverallProgressOut,
    QuizPanelActionsOut,
    StudyMaterialSummaryOut,
    SubtopicPanelItemOut,
    TraineeNodePanelOut,
)
from src.api.utils.space_node_utils.node_role_assert import (
    _assert_space_access,
    _assert_trainee,
    _get_node_and_assert_space_access,
)
from src.api.utils.trainee_progress_utils.learning_units import (
    count_completed_learning_units,
    count_learning_units,
    has_accessible_learning_content,
    subtree_has_learning_activity,
    sum_subtree_progress_percentage,
)
from src.api.utils.trainee_progress_utils.panel_rollups import (
    build_children_progress_label,
    build_overall_progress_label,
    build_subtopic_progress_badge,
)
from src.api.utils.trainee_study_utils.content_preview import build_content_preview
from src.api.utils.trainee_study_utils.node_panel_type import get_node_panel_type
from src.api.utils.trainee_study_utils.panel_labels import (
    build_availability_summary,
    build_subtopic_meta_label,
    default_mixed_parent_tab,
)
from src.api.utils.trainee_study_utils.quiz_panel_labels import (
    build_panel_back_navigation,
    build_quiz_badge,
    build_quiz_panel_actions,
    build_reading_button_label,
)
from src.api.utils.trainee_study_utils.read_time import estimate_read_time_minutes
from src.api.utils.trainee_study_utils.tree_navigation import (
    build_breadcrumbs,
    find_available_siblings,
    find_next_up,
)


class TraineeNodePanelService:
    """Assembles ``TraineeNodePanelOut`` by orchestrating study + progress services."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = TraineeNodePanelRepository(session)
        self.progress_service = TraineeProgressService(session)
        self.quiz_service = TraineeQuizService(session)

    async def get_node_panel(
        self,
        node_id: UUID,
        user_id: UUID,
        role: str,
    ) -> TraineeNodePanelOut:
        _assert_trainee(role)
        node = await _get_node_and_assert_space_access(
            self.session, node_id, user_id, owner_only=False
        )
        await _assert_space_access(self.session, node.space_id, user_id, role)

        space_nodes = await self.repo.get_active_nodes_in_space(node.space_id)
        published_ids = await self.repo.get_published_node_ids(node.space_id)
        node_by_id = {item.node_id: item for item in space_nodes}

        children_by_parent: dict[UUID | None, list[UUID]] = {}
        for item in space_nodes:
            children_by_parent.setdefault(item.parent_id, []).append(item.node_id)
        for child_ids in children_by_parent.values():
            child_ids.sort(key=lambda child_id: node_by_id[child_id].order_index)

        direct_children = [
            node_by_id[child_id]
            for child_id in children_by_parent.get(node.node_id, [])
            if child_id in node_by_id
        ]
        has_material = node.node_id in published_ids
        panel_type = get_node_panel_type(
            has_study_material=has_material,
            child_count=len(direct_children),
        )

        all_descendant_ids: list[UUID] = []

        def collect_desc(node_uuid: UUID) -> None:
            for child_id in children_by_parent.get(node_uuid, []):
                all_descendant_ids.append(child_id)
                collect_desc(child_id)

        collect_desc(node.node_id)
        progress_scope = list({node.node_id, *all_descendant_ids})

        # Option 1: progress domain accessed only through TraineeProgressService.
        progress_by_node = await self.progress_service.get_batch_node_progress(
            node_ids=progress_scope,
            user_id=user_id,
            role=role,
        )
        quiz_published_node_ids = (
            await self.progress_service.quiz_repo.get_published_quiz_node_ids(
                progress_scope
            )
        )

        ancestors = await self.repo.get_ancestors(node)
        breadcrumb_chain = build_breadcrumbs(node, ancestors)
        breadcrumbs = [
            BreadcrumbItemOut(node_id=item_id, title=title)
            for item_id, title in breadcrumb_chain
        ]
        back_nav_raw = build_panel_back_navigation(breadcrumb_chain)
        back_navigation = (
            NavSuggestionOut(**back_nav_raw) if back_nav_raw is not None else None
        )

        node_progress = progress_by_node.get(node.node_id)
        study_material_summary = await self._build_study_material_summary(
            node.node_id, user_id, role, node_progress
        )

        subtopics = [
            self._build_subtopic_item(
                child,
                published_ids=published_ids,
                children_by_parent=children_by_parent,
                progress_by_node=progress_by_node,
                quiz_published_node_ids=quiz_published_node_ids,
            )
            for child in direct_children
        ]

        available_count = sum(1 for item in subtopics if item.is_published)
        locked_count = len(subtopics) - available_count
        all_subtopics_locked = len(subtopics) > 0 and available_count == 0

        completed_available = 0
        for child in direct_children:
            if not has_accessible_learning_content(
                child.node_id, published_ids, children_by_parent
            ):
                continue
            total_units = count_learning_units(
                child.node_id, published_ids, children_by_parent
            )
            if total_units == 0:
                continue
            done_units = count_completed_learning_units(
                child.node_id,
                published_ids,
                children_by_parent,
                progress_by_node,
                quiz_published_node_ids=quiz_published_node_ids,
            )
            if done_units >= total_units:
                completed_available += 1

        overall = self._build_overall_progress(
            node.node_id,
            published_ids=published_ids,
            children_by_parent=children_by_parent,
            progress_by_node=progress_by_node,
            quiz_published_node_ids=quiz_published_node_ids,
        )

        siblings = await self.repo.get_siblings(node)
        parent_node = node_by_id.get(node.parent_id) if node.parent_id else None
        sibling_suggestions = [
            NavSuggestionOut(node_id=item_id, title=title)
            for item_id, title in find_available_siblings(
                node,
                siblings,
                published_ids,
                children_by_parent,
                limit=2,
            )
        ]
        next_up_raw = find_next_up(
            node,
            siblings,
            published_ids,
            children_by_parent,
            parent=parent_node,
        )
        next_up = (
            NavSuggestionOut(
                node_id=next_up_raw[0],
                title=next_up_raw[1],
                label_prefix=next_up_raw[2],
            )
            if next_up_raw
            else None
        )

        header_meta = self._build_header_meta(
            panel_type=panel_type,
            child_count=len(direct_children),
            available_count=available_count,
        )
        default_tab = None
        if panel_type == "mixed-parent" and study_material_summary is not None:
            default_tab = default_mixed_parent_tab(
                study_material_completed=study_material_summary.is_fully_read
            )

        is_fully_complete = (
            study_material_summary is not None
            and study_material_summary.is_fully_read
            and (
                not study_material_summary.quiz_available
                or study_material_summary.quiz_passed
            )
        )

        return TraineeNodePanelOut(
            panel_type=panel_type,
            title=node.title,
            header_meta=header_meta,
            study_material=study_material_summary,
            subtopics=subtopics,
            availability_summary=(
                build_availability_summary(
                    available_count=available_count,
                    locked_count=locked_count,
                )
                if subtopics
                else None
            ),
            children_progress_label=build_children_progress_label(
                completed_available=completed_available,
                available_count=available_count,
            ),
            breadcrumbs=breadcrumbs,
            back_navigation=back_navigation,
            sibling_suggestions=sibling_suggestions,
            next_up=next_up,
            overall_progress=overall,
            default_tab=default_tab,
            all_subtopics_locked=all_subtopics_locked,
            is_fully_complete=is_fully_complete,
        )

    async def _build_study_material_summary(
        self,
        node_id: UUID,
        user_id: UUID,
        role: str,
        progress: TraineeNodeProgressBatchItemOut | None,
    ) -> StudyMaterialSummaryOut | None:
        version = await self.repo.get_published_study_material(node_id)
        if version is None:
            return None

        snapshot = progress or TraineeNodeProgressBatchItemOut(node_id=node_id)

        quiz_discovery = await self.quiz_service.get_published_quiz_state(
            node_id, user_id, role
        )
        quiz_available = quiz_discovery.quiz_id is not None
        quiz_badge_kind, quiz_badge_label = build_quiz_badge(
            quiz_available=quiz_available,
            quiz_passed=snapshot.quiz_passed,
            has_in_progress_attempt=quiz_discovery.has_in_progress_attempt,
        )
        quiz_actions_raw = build_quiz_panel_actions(quiz_discovery)
        quiz_actions = (
            QuizPanelActionsOut(**quiz_actions_raw)
            if quiz_actions_raw is not None
            else None
        )

        return StudyMaterialSummaryOut(
            content_preview=build_content_preview(version.content),
            read_time_minutes=estimate_read_time_minutes(version.content),
            read_percent=snapshot.study_material_read_percent,
            is_fully_read=snapshot.study_material_completed,
            quiz_available=quiz_available,
            quiz_passed=snapshot.quiz_passed,
            quiz_badge_kind=quiz_badge_kind,
            quiz_badge_label=quiz_badge_label,
            reading_button_label=build_reading_button_label(
                read_percent=snapshot.study_material_read_percent
            ),
            quiz_actions=quiz_actions,
            completion_status=snapshot.completion_status,
            progress_percentage=snapshot.progress_percentage,
        )

    def _build_subtopic_item(
        self,
        child: TopicNode,
        *,
        published_ids: set[UUID],
        children_by_parent: dict[UUID | None, list[UUID]],
        progress_by_node: dict[UUID, TraineeNodeProgressBatchItemOut],
        quiz_published_node_ids: set[UUID],
    ) -> SubtopicPanelItemOut:
        is_accessible = has_accessible_learning_content(
            child.node_id, published_ids, children_by_parent
        )
        child_count = len(children_by_parent.get(child.node_id, []))
        lesson_count = count_learning_units(
            child.node_id, published_ids, children_by_parent
        )
        completed_units = count_completed_learning_units(
            child.node_id,
            published_ids,
            children_by_parent,
            progress_by_node,
            quiz_published_node_ids=quiz_published_node_ids,
        )
        total_units = count_learning_units(
            child.node_id, published_ids, children_by_parent
        )
        progress_sum = sum_subtree_progress_percentage(
            child.node_id, published_ids, children_by_parent, progress_by_node
        )
        subtree_avg_percent = (
            round(progress_sum / total_units) if total_units > 0 else 0
        )
        badge_kind, badge_label = build_subtopic_progress_badge(
            is_published=is_accessible,
            completed_units=completed_units,
            total_units=total_units,
            progress=progress_by_node.get(child.node_id),
            has_subtree_activity=subtree_has_learning_activity(
                child.node_id,
                published_ids,
                children_by_parent,
                progress_by_node,
            ),
            subtree_avg_percent=subtree_avg_percent,
        )
        return SubtopicPanelItemOut(
            node_id=child.node_id,
            title=child.title,
            is_published=is_accessible,
            lesson_count=lesson_count,
            child_count=child_count,
            meta_label=build_subtopic_meta_label(
                is_published=is_accessible,
                lesson_count=lesson_count,
                child_count=child_count,
            ),
            badge_kind=badge_kind,
            badge_label=badge_label,
        )

    def _build_overall_progress(
        self,
        node_id: UUID,
        *,
        published_ids: set[UUID],
        children_by_parent: dict[UUID | None, list[UUID]],
        progress_by_node: dict[UUID, TraineeNodeProgressBatchItemOut],
        quiz_published_node_ids: set[UUID],
    ) -> OverallProgressOut | None:
        total_units = count_learning_units(node_id, published_ids, children_by_parent)
        if total_units == 0:
            return None
        completed_units = count_completed_learning_units(
            node_id,
            published_ids,
            children_by_parent,
            progress_by_node,
            quiz_published_node_ids=quiz_published_node_ids,
        )
        # Weighted-average progress: sum each unit's 0-100 progress_percentage
        # then divide by the number of units.  This correctly handles:
        #   - units with no quiz (100% when read)
        #   - units with a quiz (50% when read, 100% when read+passed)
        #   - mixed subtrees with any combination of the above
        progress_sum = sum_subtree_progress_percentage(
            node_id, published_ids, children_by_parent, progress_by_node
        )
        percentage = round(progress_sum / total_units)
        return OverallProgressOut(
            completed_units=completed_units,
            total_units=total_units,
            percentage=percentage,
            label=build_overall_progress_label(
                completed_units=completed_units,
                total_units=total_units,
                percentage=percentage,
            ),
        )

    @staticmethod
    def _build_header_meta(
        *,
        panel_type: str,
        child_count: int,
        available_count: int,
    ) -> str:
        if panel_type == "mixed-parent":
            return f"Study material + {child_count} subtopic{'s' if child_count != 1 else ''}"
        if panel_type == "pure-parent":
            unit = "subtopic" if child_count != 1 else "subtopic"
            return f"{child_count} {unit}{'s' if child_count != 1 else ''}"
        if panel_type == "leaf-available":
            return "Study material"
        return "Coming soon"
