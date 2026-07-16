from datetime import datetime
from pathlib import Path
from typing import Final, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from code_automations.models.configuration import AutomationTarget, LoadedConfiguration
from code_automations.models.execution import PublishedPullRequest

__all__: Final[tuple[str, ...]] = (
    "AutomationState",
    "DispatchOutcome",
    "DueAutomation",
    "ScheduledDispatch",
    "SubmittedAutomation",
    "ExecutionRequest",
    "ExecutionResult",
)


class AutomationState(BaseModel):
    """Track successful scheduled submissions."""

    model_config = ConfigDict(extra="forbid", strict=True)

    version: Literal[1] = 1
    successful: dict[str, AwareDatetime] = Field(default_factory=dict)


class DueAutomation(BaseModel):
    """Describe one due scheduled automation."""

    model_config = ConfigDict(frozen=True)

    target: AutomationTarget
    scheduled_for: datetime


class ExecutionRequest(BaseModel):
    """Describe one local Codex execution."""

    model_config = ConfigDict(frozen=True)

    loaded: LoadedConfiguration
    target: AutomationTarget
    scheduled_for: datetime | None = None


class ExecutionResult(BaseModel):
    """Capture a completed automation execution."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    summary: str
    pull_requests: list[PublishedPullRequest]


class SubmittedAutomation(BaseModel):
    """Pair an automation with its execution result."""

    model_config = ConfigDict(frozen=True)

    name: str
    result: ExecutionResult


class DispatchOutcome(BaseModel):
    """Collect successful submissions and failures."""

    model_config = ConfigDict(frozen=True)

    submissions: list[SubmittedAutomation]
    failures: list[str]


class ScheduledDispatch(BaseModel):
    """Group the inputs for one scheduled dispatch operation."""

    model_config = ConfigDict(frozen=True)

    loaded: LoadedConfiguration
    due: list[DueAutomation]
    state: AutomationState
    state_path: Path
