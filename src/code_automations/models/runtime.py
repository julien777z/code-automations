import logging
from datetime import datetime
from pathlib import Path
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)

__all__: Final[tuple[str, ...]] = (
    "ActionsContext",
    "CliArguments",
    "DueAutomation",
    "PreparedRepository",
)


class ActionsContext(BaseSettings):
    """Read GitHub Actions context used by the command-line interface."""

    model_config = SettingsConfigDict(extra="ignore")

    github_repository: str | None = Field(default=None, validation_alias="GITHUB_REPOSITORY")
    github_step_summary: Path | None = Field(default=None, validation_alias="GITHUB_STEP_SUMMARY")


class CliArguments(BaseModel):
    """Validate parsed command-line arguments."""

    model_config = ConfigDict(extra="forbid", strict=True)

    config: Path
    prompts_directory: Path
    command: Literal["validate", "render", "due", "dispatch"]
    automation: str | None = None
    scheduled: bool = False
    now: str | None = None
    dispatcher_schedule: str | None = None
    workspace: Path | None = None
    agent_home: Path | None = None


class PreparedRepository(BaseModel):
    """Describe one repository prepared for an automation session."""

    model_config = ConfigDict(frozen=True)

    repository: str
    branch: str
    path: Path


class DueAutomation(BaseModel):
    """Describe one due scheduled automation."""

    model_config = ConfigDict(frozen=True)

    name: str
    scheduled_for: datetime
