from typing import Final

from pydantic_settings import BaseSettings, SettingsConfigDict

__all__: Final[tuple[str, ...]] = ("GitHubRuntime",)


class GitHubRuntime(BaseSettings):
    """Read GitHub Actions runtime settings."""

    model_config = SettingsConfigDict(env_prefix="", extra="ignore")

    github_repository: str | None = None
    github_step_summary: str | None = None
