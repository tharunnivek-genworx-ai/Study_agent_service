# Central model registry — importing every model module registers ORM classes
# on Base.metadata so SQLAlchemy can resolve cross-table foreign keys.

from src.api.data.models.postgres.e_learning_content import (  # noqa: F401
    node_media,
    quiz_attempts,
    quiz_question_responses,
    quiz_questions,
    quizzes,
    reference_llamaparse_images,
    reference_llamaparse_pdf,
    reference_materials,
    study_material_versions,
)
from src.api.data.models.postgres.e_spaces_trees import (  # noqa: F401
    espaces,
    space_trainees,
    topic_nodes,
)
from src.api.data.models.postgres.generation import (  # noqa: F401
    generation_runs,
)
from src.api.data.models.postgres.identity_refs import (  # noqa: F401
    departments,
    mentors,
    trainees,
)
from src.api.data.models.postgres.progress_models import (  # noqa: F401
    trainee_node_progress,
    trainee_space_progress,
)
