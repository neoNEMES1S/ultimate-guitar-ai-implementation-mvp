from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    data_dir: Path = Path("data")
    celery_broker_url: str = "redis://localhost:6379/0"
    celery_result_backend: str = "redis://localhost:6379/1"
    celery_task_always_eager: bool = False
    max_audio_bytes: int = 100 * 1024 * 1024

    @property
    def database_path(self) -> Path:
        return self.data_dir / "jobs.sqlite3"


settings = Settings()
