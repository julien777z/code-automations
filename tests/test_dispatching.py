from datetime import UTC, datetime, timedelta
from pathlib import Path

from cloud_automations.dispatching import dispatch_due
from cloud_automations.errors import DispatchError
from cloud_automations.models.configuration import LoadedConfiguration
from cloud_automations.models.dispatching import (
    AutomationState,
    ScheduledDispatch,
    SubmissionRequest,
    SubmissionResult,
)
from cloud_automations.scheduling import due_automations
from cloud_automations.state import load_state
from cloud_automations.targets import resolve_targets


class TestDispatching:
    """Test scheduled Cloud task submission."""

    def test_failed_submission_retries_without_advancing_state(
        self, scheduled_configuration: LoadedConfiguration, tmp_path: Path
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

        def fail(request: SubmissionRequest) -> SubmissionResult:
            """Fail one test submission."""

            assert request.target.name == "scheduled"

            raise DispatchError("submission failed")

        failed = dispatch_due(scheduled_dispatch, fail)

        assert failed.failures == ["scheduled: submission failed"]
        assert state.successful == {}
        assert not state_path.exists()
        assert len(due_automations(automation_targets, state, now + timedelta(minutes=1))) == 1

        def succeed(request: SubmissionRequest) -> SubmissionResult:
            """Accept one test submission."""

            assert request.prompt.endswith("Run the task.\n")

            return SubmissionResult(task_url="https://chatgpt.com/codex/tasks/task_example")

        successful = dispatch_due(scheduled_dispatch, succeed)

        assert successful.failures == []
        assert load_state(state_path).successful["scheduled"] == due[0].scheduled_for
