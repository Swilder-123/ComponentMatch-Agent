"""Read configuration from process environment; never load credentials from source."""

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Process-only configuration for matching and the DeepSeek/LangGraph workflow."""

    model_config = SettingsConfigDict(env_file=None, extra="ignore")

    deepseek_api_key: SecretStr | None = None
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-flash"
    llm_timeout_seconds: float = Field(default=20, gt=0, le=60)
    llm_max_retries: int = Field(default=1, ge=0, le=2)
    llm_max_tokens: int = Field(default=4096, ge=256, le=16384)
    agent_timeout_seconds: float = Field(default=90, gt=0, le=180)
    database_url: str = "sqlite:///./data/componentmatch.db"
