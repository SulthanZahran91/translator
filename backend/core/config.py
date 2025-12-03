"""Application configuration using Pydantic settings."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Application
    app_name: str = "Document Translator"
    debug: bool = False
    
    # API
    api_v1_prefix: str = "/api/v1"
    
    # Database
    database_url: str = "sqlite+aiosqlite:///./storage/db/translator.db"
    
    # Authentication
    secret_key: str = "change-this-in-production-use-a-real-secret-key"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24  # 24 hours
    refresh_token_expire_days: int = 30
    
    # LLM Configuration
    llm_api_url: str = "http://localhost:8001/v1"
    llm_api_key: str = "not-needed-for-local"
    llm_model: str = "exaone"
    llm_max_retries: int = 10
    llm_retry_base_delay: float = 1.0
    llm_retry_max_delay: float = 60.0
    
    # Upstream LLM Integration
    upstream_auth_url: str = "http://localhost:8001/auth"
    upstream_completion_url: str = "http://localhost:8001/completion"
    
    # Translation Pipeline
    max_tokens_per_unit: int = 25000
    glossary_token_budget: int = 3000
    context_tail_tokens: int = 2000
    checkpoint_interval: int = 10
    
    # Storage
    storage_type: Literal["local", "s3"] = "local"
    storage_path: Path = Path("./storage")
    max_upload_size_mb: int = 50
    
    # Directories (derived from storage_path)
    @property
    def uploads_dir(self) -> Path:
        return self.storage_path / "uploads"
    
    @property
    def outputs_dir(self) -> Path:
        return self.storage_path / "outputs"
    
    @property
    def checkpoints_dir(self) -> Path:
        return self.storage_path / "checkpoints"
    
    @property
    def temp_dir(self) -> Path:
        return self.storage_path / "temp"
    
    @property
    def db_dir(self) -> Path:
        return self.storage_path / "db"
    
    def ensure_directories(self) -> None:
        """Create all necessary storage directories."""
        for directory in [
            self.uploads_dir,
            self.outputs_dir,
            self.checkpoints_dir,
            self.temp_dir,
            self.db_dir,
        ]:
            directory.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    settings = Settings()
    settings.ensure_directories()
    return settings

