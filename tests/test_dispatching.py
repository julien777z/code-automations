from datetime import UTC, datetime
from pathlib import Path

import pytest

from code_automations.dispatching import dispatch_due
from code_automations.errors import DispatchError
from code_automations.models.configuration import AutomationTarget, LoadedConfiguration
from code_automations.models.dispatching import (
    DueAutomation,
    ExecutionRequest,
    ExecutionResult,
    ScheduledDispatch,
)
from code_automations.models.runtime import DispatchRuntime
from code_automations.scheduling import due_automations
from code_automations.targets import resolve_targets


class TestDispatching:
    """Test fail-fast scheduled automation execution."""

    def test_failed_execution_stops_dispatch(
        self,
        scheduled_configuration: LoadedConfiguration,
        tmp_path: Path,
    ) -> None:
        """Propagate the first execution failure."""

        target = resolve_targets(scheduled_configuration, "owner/repository")[0]
        now = datetime(2025, 7, 15, 18, 0, tzinfo=UTC)
        due = due_automations([target], now)
        scheduled_dispatch = ScheduledDispatch(
            loaded=scheduled_configuration,
            due=due,
        )

        runtime = self.runtime(tmp_path)

        def fail(request: ExecutionRequest, received_runtime: DispatchRuntime) -> ExecutionResult:
            """Fail one test execution."""

            assert request.target.name == "scheduled"
            assert received_runtime is runtime

            raise DispatchError("execution failed")

        with pytest.raises(DispatchError, match="execution failed"):
            dispatch_due(scheduled_dispatch, runtime, fail)

    def test_earlier_success_is_reported_before_a_later_failure(
        self,
        scheduled_configuration: LoadedConfiguration,
        tmp_path: Path,
    ) -> None:
        """Report completed work while stopping before remaining automations."""

        target = resolve_targets(scheduled_configuration, "owner/repository")[0]
        first = self.named_target(target, "first")
        second = self.named_target(target, "second")
        third = self.named_target(target, "third")
        scheduled_for = datetime(2025, 7, 15, 18, 0, tzinfo=UTC)
        scheduled_dispatch = ScheduledDispatch(
            loaded=scheduled_configuration,
            due=[
                DueAutomation(target=first, scheduled_for=scheduled_for),
                DueAutomation(target=second, scheduled_for=scheduled_for),
                DueAutomation(target=third, scheduled_for=scheduled_for),
            ],
        )

        runtime = self.runtime(tmp_path)
        executed: list[str] = []
        reported: list[str] = []

        def execute(request: ExecutionRequest, received_runtime: DispatchRuntime) -> ExecutionResult:
            """Complete the first execution and fail the second."""

            assert received_runtime is runtime
            executed.append(request.target.name)

            if request.target.name == "second":
                raise DispatchError("execution failed")

            return ExecutionResult(summary="Completed.", pull_requests=[])

        with pytest.raises(DispatchError, match="execution failed"):
            dispatch_due(
                scheduled_dispatch,
                runtime,
                execute,
                lambda submission: reported.append(submission.name),
            )

        assert executed == ["first", "second"]
        assert reported == ["first"]

    def runtime(self, tmp_path: Path) -> DispatchRuntime:
        """Build a complete dispatch runtime."""

        return DispatchRuntime(
            github_token="token",
            command_path="/bin",
            github_home=tmp_path / "github-home",
            codex_home=tmp_path / "codex-home",
            runner_image="code-automations-runner:123",
            runner_user="1001:1001",
            runner_temp=tmp_path,
            github_run_id="123",
            github_run_attempt="1",
        )

    def named_target(self, target: AutomationTarget, name: str) -> AutomationTarget:
        """Copy a target with a test-specific globally unique name."""

        return target.model_copy(update={"name": name})
