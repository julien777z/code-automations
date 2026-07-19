import logging
from datetime import datetime
from typing import Final

from pydantic import BaseModel, ConfigDict

from code_automations.models.configuration import AutomationTarget, LoadedConfiguration
from code_automations.models.execution import PublishedPullRequest

logger = logging.getLogger(__name__)

__all__: Final[tuple[str, ...]] = (
    "DueAutomation",
    "ScheduledDispatch",
    "SubmittedAutomation",
    "ExecutionRequest",
    "ExecutionResult",
)


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


class ScheduledDispatch(BaseModel):
    """Group the inputs for one scheduled dispatch operation."""

    model_config = ConfigDict(frozen=True)

    loaded: LoadedConfiguration
    due: list[DueAutomation]
