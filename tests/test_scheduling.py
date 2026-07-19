from datetime import UTC, datetime

import pytest

from code_automations.models.configuration import LoadedConfiguration, ScheduleConfig
from code_automations.scheduling import due_automations, latest_occurrence
from code_automations.targets import resolve_targets


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

    def test_due_uses_current_occurrence(self, scheduled_configuration: LoadedConfiguration) -> None:
        """Select an occurrence scheduled for the current minute."""

        automation_targets = resolve_targets(scheduled_configuration, "owner/repository")
        now = datetime(2025, 7, 15, 18, 0, tzinfo=UTC)

        due = due_automations(automation_targets, now)

        assert len(due) == 1
        assert due[0].scheduled_for == datetime(2025, 7, 15, 18, 0, tzinfo=UTC)

    def test_missed_occurrences_are_not_due(self, scheduled_configuration: LoadedConfiguration) -> None:
        """Do not catch up an occurrence missed by an earlier dispatcher run."""

        automation_targets = resolve_targets(scheduled_configuration, "owner/repository")
        now = datetime(2025, 7, 15, 18, 1, tzinfo=UTC)

        assert due_automations(automation_targets, now) == []

    def test_disabled_automation_is_not_scheduled(self, scheduled_configuration: LoadedConfiguration) -> None:
        """Suppress scheduled execution while preserving the configured target."""

        automation_targets = resolve_targets(scheduled_configuration, "owner/repository")
        automation_targets[0].automation.enabled = False

        assert due_automations(automation_targets, datetime.now(UTC)) == []
        assert automation_targets[0].name == "scheduled"

    def test_latest_occurrence_requires_an_aware_datetime(self) -> None:
        """Reject ambiguous naive scheduling instants."""

        schedule = ScheduleConfig(cron="0 9 * * *", timezone="UTC")

        with pytest.raises(ValueError, match="timezone-aware"):
            latest_occurrence(schedule, datetime(2025, 1, 1))
