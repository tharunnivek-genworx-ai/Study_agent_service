from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

import src.api.data.models.postgres  # noqa: F401 — register all ORM models on startup
from src.api.rest.middleware.cors import setup_cors
from src.api.rest.routes import health, sse, websocket
from src.api.rest.routes.quiz_routes import hint_route, quiz_route
from src.api.rest.routes.study_agent_routes import (
    reference_material_route,
    study_material_route,
)
from src.api.rest.routes.trainee_routes import progress_route, trainee_routes

app = FastAPI(title="Study Agent Service")

setup_cors(app)

app.include_router(health.router)
app.include_router(study_material_route.router)
app.include_router(reference_material_route.router)
app.include_router(quiz_route.router)
app.include_router(hint_route.router)
app.include_router(trainee_routes.router)
app.include_router(progress_route.router)
app.include_router(sse.router)
app.include_router(websocket.router)

# Serve uploaded files (reference PDFs and extracted images) over HTTP so the
# frontend can render images embedded in generated study material.
_UPLOADS_DIR = Path("/app/uploads")
_ARTIFACTS_DIR = _UPLOADS_DIR / "artifacts"
_UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
_ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=str(_UPLOADS_DIR)), name="uploads")
