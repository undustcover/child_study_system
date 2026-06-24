from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    app_name: str = "Children Learning Planner P1-A"
    app_version: str = "0.01"
    data_dir: Path = PROJECT_ROOT / "data"
    database_url: str | None = None

    model_config = SettingsConfigDict(env_file=".env", env_prefix="CHILDREN_TODO_")

    @property
    def resolved_database_url(self) -> str:
        if self.database_url:
            return self.database_url
        return f"sqlite:///{self.data_dir / 'app.db'}"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
