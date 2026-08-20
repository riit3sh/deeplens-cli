"""Central configuration loaded from environment or supplied programmatically."""

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    tavily_api_key: str | None = None
    firecrawl_api_key: str | None = None
    openai_api_key: str | None = None
    openai_base_url: str | None = None
    deeplens_model: str | None = None
    max_perspectives: int = Field(default=4, ge=1, le=5)
    max_queries_per_perspective: int = Field(default=5, ge=1, le=10)
    max_sources_per_perspective: int = Field(default=12, ge=1, le=30)
    max_followup_rounds: int = Field(default=1, ge=0, le=3)
    request_timeout_seconds: float = Field(default=20, gt=0)
    retry_count: int = Field(default=2, ge=0, le=5)
    output_dir: Path = Path("reports")

    @property
    def has_live_search(self) -> bool:
        return bool(self.tavily_api_key)
