from datetime import datetime
from pathlib import Path
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict

__all__: Final[tuple[str, ...]] = ("CliArguments", "DueRecord", "DueRepository")


class DueRecord(BaseModel):
    """Serialize one due automation."""

    model_config = ConfigDict(extra="forbid", strict=True)

    automation: str
    project: str
    repositories: list["DueRepository"]
    scheduled_for: datetime


class CliArguments(BaseModel):
    """Define typed command-line arguments."""

    model_config = ConfigDict(extra="forbid", strict=True)

    config: Path
    command: Literal["validate", "render", "due", "dispatch"]
    automation: str | None = None
    scheduled: bool = False
    state: Path | None = None
    now: str | None = None


class DueRepository(BaseModel):
    """Serialize one repository due for an automation."""

    model_config = ConfigDict(extra="forbid", strict=True)

    repository: str
    branch: str
