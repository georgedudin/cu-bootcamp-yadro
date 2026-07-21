from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """All knobs come from environment variables (see infra/.env.example)."""

    database_url: str = "postgresql+psycopg://yadro:yadro@localhost:5432/yadro"
    redis_url: str = "redis://localhost:6379/0"
    blob_dir: str = "/blob"

    chunk_window_s: float = 45.0
    chunk_overlap_s: float = 5.0
    target_sr: int = 16000

    max_chunk_retries: int = 3


@lru_cache
def get_settings() -> Settings:
    return Settings()
