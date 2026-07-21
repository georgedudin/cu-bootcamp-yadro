"""FastAPI app. No CORS middleware on purpose: nginx serves the frontend and
reverse-proxies /api to this service, so the browser sees one origin."""

from contextlib import asynccontextmanager

from fastapi import FastAPI

from backend.api.recordings import router
from core.session import get_engine


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    get_engine().dispose()


app = FastAPI(title="YADRO ASR + diarization", lifespan=lifespan)
app.include_router(router, prefix="/api")


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}
