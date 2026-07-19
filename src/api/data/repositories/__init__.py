"""Repository layer for Study Agent Service persistence."""

from src.api.data.repositories.generation_run_repository import GenerationRunRepository
from src.api.data.repositories.progress_repositories.mentor_progress_repository import (
    MentorProgressRepository,
)
from src.api.data.repositories.progress_repositories.trainee_node_progress_repository import (
    TraineeNodeProgressRepository,
)
from src.api.data.repositories.progress_repositories.trainee_node_unlock_repository import (
    TraineeNodeUnlockRepository,
)
from src.api.data.repositories.progress_repositories.trainee_space_progress_repository import (
    TraineeSpaceProgressRepository,
)
from src.api.data.repositories.quiz_repositories.hint_repository import HintRepository
from src.api.data.repositories.quiz_repositories.quiz_repository import QuizRepository
from src.api.data.repositories.space_node_repository.node_repository import (
    NodeRepository,
)
from src.api.data.repositories.space_node_repository.space_repository import (
    SpaceRepository,
)
from src.api.data.repositories.study_agent_repositories.external_research_repository import (
    ExternalResearchRepository,
)
from src.api.data.repositories.study_agent_repositories.reference_llamaparse_repository import (
    ReferenceLlamaParseRepository,
)
from src.api.data.repositories.study_agent_repositories.reference_material_repository import (
    ReferenceMaterialRepository,
)
from src.api.data.repositories.study_agent_repositories.study_material_repository import (
    StudyMaterialRepository,
)
from src.api.data.repositories.trainee_quiz_repositories.trainee_quiz_repository import (
    TraineeQuizRepository,
)
from src.api.data.repositories.trainee_study_repositories.trainee_node_panel_repository import (
    TraineeNodePanelRepository,
)
from src.api.data.repositories.trainee_study_repositories.trainee_study_repository import (
    TraineeStudyRepository,
)

__all__ = [
    "ExternalResearchRepository",
    "GenerationRunRepository",
    "HintRepository",
    "MentorProgressRepository",
    "NodeRepository",
    "QuizRepository",
    "ReferenceLlamaParseRepository",
    "ReferenceMaterialRepository",
    "SpaceRepository",
    "StudyMaterialRepository",
    "TraineeNodePanelRepository",
    "TraineeNodeProgressRepository",
    "TraineeNodeUnlockRepository",
    "TraineeQuizRepository",
    "TraineeSpaceProgressRepository",
    "TraineeStudyRepository",
]
