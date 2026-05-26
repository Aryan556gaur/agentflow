from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://agentflow:agentflow_secret@localhost:5432/agentflow"
    redis_url: str = "redis://localhost:6379"
    gemini_api_key: str = ""
    telegram_bot_token: str = ""
    secret_key: str = "supersecretkey123"
    debug: bool = True

    class Config:
        env_file = ".env"


@lru_cache
def get_settings() -> Settings:
    return Settings()
