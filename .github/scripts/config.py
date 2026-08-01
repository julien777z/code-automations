from pathlib import Path
from typing import Literal, Self

from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class ValidationConfig(BaseSettings):
    """Validate inputs and GitHub event context for one action invocation."""

    model_config = SettingsConfigDict(extra="ignore", frozen=True)

    automation_mode: Literal["validate", "dispatch"]
    automations_file_path: Path
    prompts_directory_path: Path
    default_branch: str
    github_event_name: str
    github_ref: str
    github_workspace: Path

    @model_validator(mode="after")
    def validate_dispatch(self) -> Self:
        """Require supported events and credentials for dispatch mode."""

        if self.automation_mode != "dispatch":
            return self

        if self.github_event_name == "schedule":
            if self.github_ref != f"refs/heads/{self.default_branch}":
                raise ValueError("scheduled dispatch is only allowed from the default branch")
        elif self.github_event_name != "workflow_dispatch":
            raise ValueError("dispatch is only allowed for scheduled and manual workflow runs")

        return self


class AuthenticationConfig(BaseSettings):
    """Provide validated settings for temporary Codex authentication."""

    model_config = SettingsConfigDict(extra="ignore", frozen=True)

    codex_auth_json: SecretStr
    github_output: Path
    runner_temp: Path


class DispatchConfig(BaseSettings):
    """Provide validated settings for one automation dispatch."""

    model_config = SettingsConfigDict(extra="ignore", frozen=True)

    automations_file_path: Path
    codex_environment_id: str
    github_action_path: Path
    github_event_schedule: str = ""
    github_ref_name: str
    github_workspace: Path
    path: str
    prompts_directory_path: Path
    run_automation: str = ""


class CleanupConfig(BaseSettings):
    """Provide validated settings for temporary authentication cleanup."""

    model_config = SettingsConfigDict(extra="ignore", frozen=True)

    authentication_home: Path | None = None
    runner_temp: Path
