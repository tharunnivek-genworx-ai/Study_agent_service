from fastapi import FastAPI

from .routes import health, sse, websocket

app = FastAPI()

app.include_router(health.router)
app.include_router(sse.router)
app.include_router(websocket.router)
