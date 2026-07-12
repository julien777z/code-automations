import re
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Final

from pydantic import BaseModel, ConfigDict, HttpUrl

from cloud_automations.configuration import AutomationTarget, LoadedConfiguration
from cloud_automations.errors import DispatchError
from cloud_automations.models import AutomationState
from cloud_automations.rendering import render_target
from cloud_automations.scheduling import DueAutomation
from cloud_automations.state import save_state

__all__: Final[tuple[str, ...]] = (
    "DispatchOutcome",
    "SubmittedAutomation",
    "SubmissionRequest",
    "SubmissionResult",
    "Submitter",
    "dispatch_due",
    "dispatch_target",
    "submit_cloud_task",
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


type Submitter = Callable[[SubmissionRequest], SubmissionResult]


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


def submit_cloud_task(request: SubmissionRequest) -> SubmissionResult:
    """Submit one asynchronous Codex Cloud task."""
    result = subprocess.run(
        [
            "codex",
            "cloud",
            "exec",
            "--env",
            request.target.environment,
            "--attempts",
            str(request.target.automation.attempts),
            "--branch",
            request.target.branch,
            request.prompt,
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    if result.returncode != 0:
        detail = result.stderr.strip() or "codex cloud exec failed without an error message"

        raise DispatchError(detail)

    output = result.stdout.strip()

    if not re.fullmatch(r"https://chatgpt\.com/codex/tasks/[A-Za-z0-9_-]+", output):
        raise DispatchError("codex cloud exec did not return a task URL")

    return SubmissionResult(task_url=output)


def dispatch_target(
    loaded: LoadedConfiguration, target: AutomationTarget, submitter: Submitter = submit_cloud_task
) -> SubmissionResult:
    """Render and submit one manual automation."""
    return submitter(SubmissionRequest(target=target, prompt=render_target(loaded, target)))


def dispatch_due(
    loaded: LoadedConfiguration,
    due: list[DueAutomation],
    state: AutomationState,
    state_path: Path,
    submitter: Submitter = submit_cloud_task,
) -> DispatchOutcome:
    """Submit due automations and advance state only on accepted tasks."""
    submissions: list[SubmittedAutomation] = []
    failures: list[str] = []

    for item in due:
        try:
            result = dispatch_target(loaded, item.target, submitter)
        except DispatchError as error:
            failures.append(f"{item.target.name}: {error}")
            continue

        state.successful[item.target.name] = item.scheduled_for
        save_state(state_path, state)
        submissions.append(SubmittedAutomation(name=item.target.name, result=result))

    return DispatchOutcome(submissions=submissions, failures=failures)
