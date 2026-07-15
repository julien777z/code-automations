from pathlib import Path
from typing import Final

from pydantic import BaseModel, ConfigDict, HttpUrl

from cloud_automations.models.configuration import AutomationTarget, LoadedConfiguration
from cloud_automations.models.scheduling import DueAutomation
from cloud_automations.models.state import AutomationState

__all__: Final[tuple[str, ...]] = (
    "DispatchOutcome",
    "ScheduledDispatch",
    "SubmittedAutomation",
    "SubmissionRequest",
    "SubmissionResult",
)


class SubmissionRequest(BaseModel):
    """Describe one Codex Cloud submission."""

    model_config = ConfigDict(frozen=True)

    target: AutomationTarget
    prompt: str


class SubmissionResult(BaseModel):
    """Capture a submitted Codex Cloud task URL."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    task_url: HttpUrl


class SubmittedAutomation(BaseModel):
    """Pair a submitted automation with its task result."""

    model_config = ConfigDict(frozen=True)

    name: str
    result: SubmissionResult


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
