from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Children Learning Planner P1-A"
    app_version: str = "0.01"
    data_dir: Path = Path("data")
    database_url: str = "sqlite:///data/app.db"

    model_config = SettingsConfigDict(env_file=".env", env_prefix="CHILDREN_TODO_")


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
