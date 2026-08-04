from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "汽车直播智能辅助工具"
    app_env: str = "development"
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    database_path: Path = Path("./storage/live-monitor.db")
    storage_root: Path = Path("./storage")
    web_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    asr_provider: str = "mock"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.web_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
