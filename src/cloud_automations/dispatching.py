import re
import subprocess
from collections.abc import Callable
from typing import Final

from cloud_automations.errors import DispatchError
from cloud_automations.models.configuration import AutomationTarget, LoadedConfiguration
from cloud_automations.models.dispatching import (
    DispatchOutcome,
    ScheduledDispatch,
    SubmissionRequest,
    SubmissionResult,
    SubmittedAutomation,
)
from cloud_automations.rendering import render_target
from cloud_automations.state import save_state

TASK_URL_PATTERN: Final[re.Pattern[str]] = re.compile(r"https://chatgpt\.com/codex/tasks/[A-Za-z0-9_-]+")

__all__: Final[tuple[str, ...]] = (
    "Submitter",
    "dispatch_due",
    "dispatch_target",
    "submit_cloud_task",
)


type Submitter = Callable[[SubmissionRequest], SubmissionResult]


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

    if not TASK_URL_PATTERN.fullmatch(output):
        raise DispatchError("codex cloud exec did not return a task URL")

    return SubmissionResult(task_url=output)


def dispatch_target(
    loaded: LoadedConfiguration, target: AutomationTarget, submitter: Submitter = submit_cloud_task
) -> SubmissionResult:
    """Render and submit one manual automation."""

    return submitter(SubmissionRequest(target=target, prompt=render_target(loaded, target)))


def dispatch_due(
    scheduled_dispatch: ScheduledDispatch,
    submitter: Submitter = submit_cloud_task,
) -> DispatchOutcome:
    """Submit due automations and advance state only on accepted tasks."""

    submissions: list[SubmittedAutomation] = []
    failures: list[str] = []

    for item in scheduled_dispatch.due:
        try:
            result = dispatch_target(scheduled_dispatch.loaded, item.target, submitter)
        except DispatchError as error:
            failures.append(f"{item.target.name}: {error}")
            continue

        scheduled_dispatch.state.successful[item.target.name] = item.scheduled_for

        save_state(scheduled_dispatch.state_path, scheduled_dispatch.state)

        submissions.append(SubmittedAutomation(name=item.target.name, result=result))

    return DispatchOutcome(submissions=submissions, failures=failures)
