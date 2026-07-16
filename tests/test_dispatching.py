from datetime import UTC, datetime, timedelta
from pathlib import Path

from code_automations.dispatching import dispatch_due
from code_automations.errors import DispatchError
from code_automations.models.configuration import LoadedConfiguration
from code_automations.models.dispatching import (
    AutomationState,
    ExecutionRequest,
    ExecutionResult,
    ScheduledDispatch,
)
from code_automations.models.execution import PublishedPullRequest
from code_automations.models.runtime import DispatchRuntime
from code_automations.scheduling import due_automations
from code_automations.state import load_state
from code_automations.targets import resolve_targets


class TestDispatching:
    """Test scheduled multi-repository automation execution."""

    def test_failed_execution_retries_without_advancing_state(
        self,
        scheduled_configuration: LoadedConfiguration,
        tmp_path: Path,
    ) -> None:
        """Leave failed occurrences due and advance state after a later success."""

        automation_targets = resolve_targets(scheduled_configuration, "owner/repository")
        now = datetime(2025, 7, 15, 18, 25, tzinfo=UTC)
        due = due_automations(automation_targets, AutomationState(), now)
        state_path = tmp_path / "state.json"
        state = AutomationState()
        scheduled_dispatch = ScheduledDispatch(
            loaded=scheduled_configuration,
            due=due,
            state=state,
            state_path=state_path,
        )
        runtime = DispatchRuntime(
            github_token="token",
            command_path="/bin",
            github_home=tmp_path / "github-home",
            codex_home=tmp_path,
            runner_temp=tmp_path,
            github_run_id="123",
        )

        def fail(request: ExecutionRequest, received_runtime: DispatchRuntime) -> ExecutionResult:
            """Fail one test execution."""

            assert request.target.name == "scheduled"
            assert received_runtime is runtime

            raise DispatchError("execution failed")

        failed = dispatch_due(scheduled_dispatch, runtime, fail)

        assert failed.failures == ["scheduled: execution failed"]
        assert state.successful == {}
        assert not state_path.exists()
        assert len(due_automations(automation_targets, state, now + timedelta(minutes=1))) == 1

        def succeed(request: ExecutionRequest, received_runtime: DispatchRuntime) -> ExecutionResult:
            """Complete one test execution."""

            assert request.scheduled_for == due[0].scheduled_for
            assert received_runtime is runtime

            return ExecutionResult(
                summary="Completed.",
                pull_requests=[
                    PublishedPullRequest(
                        repository="owner/repository",
                        url="https://github.com/owner/repository/pull/1",
                    )
                ],
            )

        successful = dispatch_due(scheduled_dispatch, runtime, succeed)

        assert successful.failures == []
        assert load_state(state_path).successful["scheduled"] == due[0].scheduled_for
