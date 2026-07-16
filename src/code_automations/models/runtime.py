import logging
from pathlib import Path
from typing import Final

from pydantic import BaseModel, ConfigDict, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)

__all__: Final[tuple[str, ...]] = ("ActionsRuntime", "DispatchRuntime", "resolve_dispatch_runtime")


class ActionsRuntime(BaseSettings):
    """Read GitHub Actions runtime settings."""

    model_config = SettingsConfigDict(extra="ignore")

    github_repository: str | None = Field(default=None, validation_alias="GITHUB_REPOSITORY")
    github_step_summary: str | None = Field(default=None, validation_alias="GITHUB_STEP_SUMMARY")
    github_run_id: str | None = Field(default=None, validation_alias="GITHUB_RUN_ID")
    github_run_attempt: str | None = Field(default=None, validation_alias="GITHUB_RUN_ATTEMPT")
    github_token: str | None = Field(default=None, validation_alias="AUTOMATION_GITHUB_TOKEN")
    command_path: str | None = Field(default=None, validation_alias="AUTOMATION_COMMAND_PATH")
    github_home: Path | None = Field(default=None, validation_alias="AUTOMATION_GITHUB_HOME")
    codex_home: Path | None = Field(default=None, validation_alias="AUTOMATION_CODEX_HOME")
    runner_image: str | None = Field(default=None, validation_alias="AUTOMATION_RUNNER_IMAGE")
    runner_user: str | None = Field(default=None, validation_alias="AUTOMATION_RUNNER_USER")
    runner_temp: Path | None = Field(default=None, validation_alias="RUNNER_TEMP")


class DispatchRuntime(BaseModel):
    """Provide the credentials and directories required for dispatch."""

    model_config = ConfigDict(frozen=True, strict=True)

    github_token: str
    command_path: str
    github_home: Path
    codex_home: Path
    runner_image: str
    runner_user: str
    runner_temp: Path
    github_run_id: str
    github_run_attempt: str


def resolve_dispatch_runtime(runtime: ActionsRuntime) -> DispatchRuntime:
    """Require the GitHub Actions values needed to run an automation."""

    required = (
        ("github_token", runtime.github_token),
        ("command_path", runtime.command_path),
        ("github_home", runtime.github_home),
        ("codex_home", runtime.codex_home),
        ("runner_image", runtime.runner_image),
        ("runner_user", runtime.runner_user),
        ("runner_temp", runtime.runner_temp),
        ("github_run_id", runtime.github_run_id),
        ("github_run_attempt", runtime.github_run_attempt),
    )
    missing = [name for name, value in required if value is None]

    if missing:
        raise ValueError(f"dispatch requires GitHub Actions values: {', '.join(missing)}")

    return DispatchRuntime.model_validate(runtime.model_dump(exclude_none=True))
