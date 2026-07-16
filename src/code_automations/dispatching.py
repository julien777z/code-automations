import logging
from collections.abc import Callable
from typing import Final

from code_automations.execution import run_automation, validate_agent_result
from code_automations.models.dispatching import (
    DispatchOutcome,
    ExecutionRequest,
    ExecutionResult,
    ScheduledDispatch,
    SubmittedAutomation,
)
from code_automations.models.runtime import DispatchRuntime
from code_automations.publication import changed_repositories, publish_pull_requests
from code_automations.rendering import render_target
from code_automations.state import save_state
from code_automations.workspace import create_workspace

logger = logging.getLogger(__name__)

__all__: Final[tuple[str, ...]] = ("dispatch_due", "dispatch_target", "execute_automation")


type Executor = Callable[[ExecutionRequest, DispatchRuntime], ExecutionResult]


def execute_automation(request: ExecutionRequest, runtime: DispatchRuntime) -> ExecutionResult:
    """Execute and publish one multi-repository automation."""

    workspace = create_workspace(request, runtime)
    prompt = render_target(request.loaded, request.target, workspace.repositories)
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
) -> DispatchOutcome:
    """Execute due automations and advance state only after publication succeeds."""

    submissions: list[SubmittedAutomation] = []
    failures: list[str] = []

    for item in scheduled_dispatch.due:
        request = ExecutionRequest(
            loaded=scheduled_dispatch.loaded,
            target=item.target,
            scheduled_for=item.scheduled_for,
        )

        try:
            result = dispatch_target(request, runtime, executor)
        except RuntimeError as error:
            failures.append(f"{item.target.name}: {error}")
            continue

        scheduled_dispatch.state.successful[item.target.name] = item.scheduled_for

        save_state(scheduled_dispatch.state_path, scheduled_dispatch.state)

        submissions.append(SubmittedAutomation(name=item.target.name, result=result))

    return DispatchOutcome(submissions=submissions, failures=failures)
