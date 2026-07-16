import logging
from enum import StrEnum
from pathlib import Path
from typing import Final

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator

logger = logging.getLogger(__name__)

__all__: Final[tuple[str, ...]] = (
    "AgentResult",
    "AutomationWorkspace",
    "ExistingPullRequest",
    "PullRequestOwner",
    "PullRequestRepository",
    "PullRequestMetadata",
    "PullRequestState",
    "PublishedPullRequest",
    "RepositoryWorkspace",
)


class RepositoryWorkspace(BaseModel):
    """Represent one checked-out repository workspace."""

    model_config = ConfigDict(frozen=True)

    repository: str
    branch: str
    path: Path
    starting_commit: str
    existing_branch: bool


class AutomationWorkspace(BaseModel):
    """Represent all repository workspaces for one automation run."""

    model_config = ConfigDict(frozen=True)

    root: Path
    home: Path
    branch: str
    repositories: list[RepositoryWorkspace] = Field(min_length=1)


class PullRequestMetadata(BaseModel):
    """Describe publication metadata for one changed repository."""

    model_config = ConfigDict(extra="forbid", strict=True)

    repository: str
    title: str = Field(min_length=1, max_length=256)
    body: str = Field(min_length=1)

    @field_validator("title", "body")
    @classmethod
    def validate_nonempty_text(cls, value: str) -> str:
        """Reject blank publication metadata."""

        if not value.strip():
            raise ValueError("publication metadata must not be blank")

        return value


class AgentResult(BaseModel):
    """Capture one structured Codex execution result."""

    model_config = ConfigDict(extra="forbid", strict=True)

    summary: str = Field(min_length=1)
    repositories: list[PullRequestMetadata]

    @field_validator("summary")
    @classmethod
    def validate_summary(cls, value: str) -> str:
        """Reject blank automation summaries."""

        if not value.strip():
            raise ValueError("summary must not be blank")

        return value


class PublishedPullRequest(BaseModel):
    """Capture one pull request created or updated by the workflow."""

    model_config = ConfigDict(frozen=True)

    repository: str
    url: HttpUrl


class PullRequestState(StrEnum):
    """Represent GitHub pull request states."""

    OPEN = "OPEN"
    CLOSED = "CLOSED"
    MERGED = "MERGED"


class PullRequestRepository(BaseModel):
    """Identify a repository attached to a pull request."""

    model_config = ConfigDict(extra="ignore", strict=True)

    name: str


class PullRequestOwner(BaseModel):
    """Identify the owner attached to a pull request."""

    model_config = ConfigDict(extra="ignore", strict=True)

    login: str


class ExistingPullRequest(BaseModel):
    """Represent the existing pull request for an automation branch."""

    model_config = ConfigDict(extra="forbid", strict=True)

    url: HttpUrl
    state: PullRequestState
    head_repository: PullRequestRepository | None = Field(validation_alias="headRepository")
    head_repository_owner: PullRequestOwner | None = Field(validation_alias="headRepositoryOwner")
