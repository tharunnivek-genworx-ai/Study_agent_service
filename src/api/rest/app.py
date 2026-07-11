# ruff: noqa: E402
from pathlib import Path

from src.api.observability.tracing import init_langsmith_tracing

# Initialize LangSmith tracing environment variables on startup
init_langsmith_tracing()

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

import src.api.data.models.postgres  # noqa: F401 — register all ORM models on startup
from src.api.config import feature_settings, settings
from src.api.rest.middleware.cors import setup_cors
from src.api.rest.routes import health
from src.api.rest.routes.generation_progress_route import (
    router as generation_progress_router,
)
from src.api.rest.routes.generation_run_route import router as generation_run_router
from src.api.rest.routes.media_access_route import router as media_access_router
from src.api.rest.routes.progress_routes import (
    mentor_progress_route,
    trainee_progress_route,
    trainee_space_progress_route,
)
from src.api.rest.routes.quiz_routes import hint_route, quiz_route
from src.api.rest.routes.study_agent_routes import (
    reference_material_route,
    study_material_batch_route,
    study_material_route,
)
from src.api.rest.routes.trainee_quiz_routes import trainee_quiz_routes
from src.api.rest.routes.trainee_study_routes import trainee_study_routes

app = FastAPI(title="Study Agent Service")

setup_cors(app)

app.include_router(health.router)
app.include_router(media_access_router)
app.include_router(generation_progress_router)
app.include_router(generation_run_router)
app.include_router(study_material_route.router)
app.include_router(study_material_batch_route.router)
app.include_router(reference_material_route.router)
app.include_router(quiz_route.router)
app.include_router(hint_route.router)
app.include_router(trainee_quiz_routes.router)
app.include_router(trainee_study_routes.router)
app.include_router(trainee_progress_route.router)
app.include_router(trainee_space_progress_route.router)
app.include_router(mentor_progress_route.router)

# Serve uploaded files over HTTP in local mode so the frontend can render images.
# When GCS is enabled, browser access uses app media tokens or trainee API routes.
_UPLOADS_DIR = Path("/app/uploads")
_ARTIFACTS_DIR = _UPLOADS_DIR / "artifacts"
if settings.storage_backend == "local":
    _UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    if feature_settings.enable_artifact_logging:
        _ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    app.mount("/uploads", StaticFiles(directory=str(_UPLOADS_DIR)), name="uploads")
