"""Public REST and domain schemas for the Study Agent Service."""

from src.api.schemas.common import *  # noqa: F403
from src.api.schemas.common import __all__ as _common_all
from src.api.schemas.generation_progress_schema import (
    GenerationJobStatus,
    GenerationPipeline,
    GenerationProgressOut,
    GenerationProgressRecord,
    GenerationProgressStep,
    GenerationProgressStepDef,
    GenerationProgressStepOut,
    GenerationStepStatus,
)
from src.api.schemas.generation_run_schema import (
    ACTIVE_RUN_STATUSES,
    MAX_RESUME_ATTEMPTS,
    RESUMABLE_RUN_STATUSES,
    GenerationRunCancelResponse,
    GenerationRunCreate,
    GenerationRunMode,
    GenerationRunOut,
    GenerationRunPipeline,
    GenerationRunResourceType,
    GenerationRunResumeResponse,
    GenerationRunResumeResult,
    GenerationRunStatus,
)
from src.api.schemas.identity_schemas import *  # noqa: F403
from src.api.schemas.identity_schemas import __all__ as _identity_all
from src.api.schemas.progress_schemas import *  # noqa: F403
from src.api.schemas.progress_schemas import __all__ as _progress_all
from src.api.schemas.qc_schemas import *  # noqa: F403
from src.api.schemas.qc_schemas import __all__ as _qc_all
from src.api.schemas.quiz_schemas import *  # noqa: F403
from src.api.schemas.quiz_schemas import __all__ as _quiz_all
from src.api.schemas.study_material_schemas import *  # noqa: F403
from src.api.schemas.study_material_schemas import __all__ as _study_material_all

__all__ = [
    *_common_all,
    *_identity_all,
    *_progress_all,
    *_qc_all,
    *_quiz_all,
    *_study_material_all,
    "ACTIVE_RUN_STATUSES",
    "GenerationJobStatus",
    "GenerationPipeline",
    "GenerationProgressOut",
    "GenerationProgressRecord",
    "GenerationProgressStep",
    "GenerationProgressStepDef",
    "GenerationProgressStepOut",
    "GenerationRunCancelResponse",
    "GenerationRunCreate",
    "GenerationRunMode",
    "GenerationRunOut",
    "GenerationRunPipeline",
    "GenerationRunResourceType",
    "GenerationRunResumeResponse",
    "GenerationRunResumeResult",
    "GenerationRunStatus",
    "GenerationStepStatus",
    "MAX_RESUME_ATTEMPTS",
    "RESUMABLE_RUN_STATUSES",
]
