import logging
from collections.abc import Callable
from typing import Final

from code_automations.execution import container_repositories, run_automation, validate_agent_result
from code_automations.models.dispatching import (
    ExecutionRequest,
    ExecutionResult,
    ScheduledDispatch,
    SubmittedAutomation,
)
from code_automations.models.runtime import DispatchRuntime
from code_automations.publication import changed_repositories, publish_pull_requests
from code_automations.rendering import render_target
from code_automations.workspace import create_workspace

logger = logging.getLogger(__name__)

__all__: Final[tuple[str, ...]] = ("dispatch_due", "dispatch_target", "execute_automation")


type Executor = Callable[[ExecutionRequest, DispatchRuntime], ExecutionResult]
type SubmissionHandler = Callable[[SubmittedAutomation], None]


def execute_automation(request: ExecutionRequest, runtime: DispatchRuntime) -> ExecutionResult:
    """Execute and publish one multi-repository automation."""

    workspace = create_workspace(request, runtime)

    prompt = render_target(request.loaded, request.target, container_repositories(workspace))
    result = run_automation(workspace, runtime, prompt)

    changed = changed_repositories(workspace, runtime)
    changed_names = [repository.repository for repository in changed]

    validate_agent_result(result, changed_names)

    return ExecutionResult(
        summary=result.summary,
        pull_requests=publish_pull_requests(workspace, runtime, result, changed),
    )


def dispatch_target(
    request: ExecutionRequest,
    runtime: DispatchRuntime,
    executor: Executor = execute_automation,
) -> ExecutionResult:
    """Execute one manual automation."""

    return executor(request, runtime)


def dispatch_due(
    scheduled_dispatch: ScheduledDispatch,
    runtime: DispatchRuntime,
    executor: Executor = execute_automation,
    submission_handler: SubmissionHandler | None = None,
) -> list[SubmittedAutomation]:
    """Execute due automations and stop at the first failure."""

    submissions: list[SubmittedAutomation] = []

    for item in scheduled_dispatch.due:
        request = ExecutionRequest(
            loaded=scheduled_dispatch.loaded,
            target=item.target,
            scheduled_for=item.scheduled_for,
        )

        result = dispatch_target(request, runtime, executor)

        submission = SubmittedAutomation(name=item.target.name, result=result)
        submissions.append(submission)

        if submission_handler is not None:
            submission_handler(submission)

    return submissions
