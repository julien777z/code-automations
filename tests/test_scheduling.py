from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from cloud_automations.configuration import LoadedConfiguration, targets
from cloud_automations.dispatching import ScheduledDispatch, SubmissionRequest, SubmissionResult, dispatch_due
from cloud_automations.errors import DispatchError
from cloud_automations.models.configuration import ScheduleConfig
from cloud_automations.models.state import AutomationState
from cloud_automations.scheduling import due_automations, latest_occurrence
from cloud_automations.state import load_state


class TestScheduling:
    """Test timezone-aware automation scheduling."""

    def test_timezone_schedule_tracks_standard_and_daylight_offsets(self) -> None:
        """Evaluate the same local schedule across daylight-saving offsets."""

        schedule = ScheduleConfig(cron="0 9 * * *", timezone="America/Los_Angeles")

        winter = latest_occurrence(schedule, datetime(2025, 1, 15, 18, 0, tzinfo=UTC))
        summer = latest_occurrence(schedule, datetime(2025, 7, 15, 18, 0, tzinfo=UTC))

        assert winter == datetime(2025, 1, 15, 17, 0, tzinfo=UTC)
        assert summer == datetime(2025, 7, 15, 16, 0, tzinfo=UTC)

    def test_fall_back_uses_the_first_ambiguous_local_occurrence(self) -> None:
        """Preserve a missed schedule occurrence across the daylight-saving fallback."""

        schedule = ScheduleConfig(cron="30 1 * * *", timezone="America/Los_Angeles")

        occurrence = latest_occurrence(schedule, datetime(2025, 11, 2, 9, 17, tzinfo=UTC))

        assert occurrence == datetime(2025, 11, 2, 8, 30, tzinfo=UTC)

    def test_due_uses_latest_missed_occurrence_and_deduplicates(
        self, scheduled_configuration: LoadedConfiguration
    ) -> None:
        """Select the latest missed occurrence and suppress an already-recorded one."""

        automation_targets = targets(scheduled_configuration, "owner/repository")
        now = datetime(2025, 7, 15, 18, 25, tzinfo=UTC)

        due = due_automations(automation_targets, AutomationState(), now)

        assert len(due) == 1
        assert due[0].scheduled_for == datetime(2025, 7, 15, 18, 0, tzinfo=UTC)

        state = AutomationState(successful={"scheduled": due[0].scheduled_for})

        assert due_automations(automation_targets, state, now) == []

    def test_occurrences_older_than_24_hours_are_not_due(
        self, scheduled_configuration: LoadedConfiguration
    ) -> None:
        """Ignore a latest occurrence outside the catch-up window."""

        automation_targets = targets(scheduled_configuration, "owner/repository")
        automation_targets[0].automation.schedule = ScheduleConfig(cron="0 0 1 * *", timezone="UTC")
        now = datetime(2025, 7, 15, 18, 0, tzinfo=UTC)

        assert due_automations(automation_targets, AutomationState(), now) == []

    def test_disabled_automation_is_not_scheduled(self, scheduled_configuration: LoadedConfiguration) -> None:
        """Suppress scheduled execution while preserving the configured target."""

        automation_targets = targets(scheduled_configuration, "owner/repository")
        automation_targets[0].automation.enabled = False

        assert due_automations(automation_targets, AutomationState(), datetime.now(UTC)) == []
        assert automation_targets[0].name == "scheduled"

    def test_latest_occurrence_requires_an_aware_datetime(self) -> None:
        """Reject ambiguous naive scheduling instants."""

        schedule = ScheduleConfig(cron="0 9 * * *", timezone="UTC")

        with pytest.raises(ValueError, match="timezone-aware"):
            latest_occurrence(schedule, datetime(2025, 1, 1))


class TestDispatching:
    """Test scheduled Cloud task submission."""

    def test_failed_submission_retries_without_advancing_state(
        self, scheduled_configuration: LoadedConfiguration, tmp_path: Path
    ) -> None:
        """Leave failed occurrences due and advance state after a later success."""

        automation_targets = targets(scheduled_configuration, "owner/repository")
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
