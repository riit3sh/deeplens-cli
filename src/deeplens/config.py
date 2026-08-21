"""Central configuration loaded from environment or supplied programmatically."""

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

GLOBAL_CONFIG_DIR = Path.home() / ".deeplens"
GLOBAL_ENV_FILE = GLOBAL_CONFIG_DIR / ".env"

def save_global_config(updates: dict[str, str]) -> None:
    """Save updates to the global ~/.deeplens/.env file."""
    GLOBAL_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    env_vars = {}
    if GLOBAL_ENV_FILE.exists():
        for line in GLOBAL_ENV_FILE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env_vars[k.strip()] = v.strip()
    env_vars.update(updates)
    lines = [f"{k}={v}" for k, v in env_vars.items()]
    GLOBAL_ENV_FILE.write_text("\n".join(lines), encoding="utf-8")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(str(GLOBAL_ENV_FILE), ".env"), 
        env_file_encoding="utf-8", 
        extra="ignore"
    )

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
