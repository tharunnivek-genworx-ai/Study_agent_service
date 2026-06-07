from fastapi import FastAPI

app = FastAPI()

from .routes import health, sse, websocket  # noqa: F401

