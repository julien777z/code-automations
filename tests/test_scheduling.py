from datetime import UTC, datetime

from code_automations.configuration import resolve_targets
from code_automations.models.configuration import LoadedConfiguration, ScheduleConfig
from code_automations.scheduling import (
    dispatcher_occurrence,
    due_automations,
    latest_occurrence,
)


class TestScheduling:
    """Test timezone-aware stateless scheduling."""

    def test_timezone_schedule_tracks_standard_and_daylight_offsets(self) -> None:
        """Evaluate the same local schedule across daylight-saving offsets."""

        schedule = ScheduleConfig(cron="0 9 * * *", timezone="America/Los_Angeles")

        winter = latest_occurrence(schedule, datetime(2025, 1, 15, 18, 0, tzinfo=UTC))
        summer = latest_occurrence(schedule, datetime(2025, 7, 15, 18, 0, tzinfo=UTC))

        assert winter == datetime(2025, 1, 15, 17, 0, tzinfo=UTC)
        assert summer == datetime(2025, 7, 15, 16, 0, tzinfo=UTC)

    def test_dispatcher_occurrence_uses_scheduled_minute(self) -> None:
        """Map a delayed GitHub event back to its intended occurrence."""

        occurrence = dispatcher_occurrence(
            "0 18 * * *",
            datetime(2025, 7, 15, 18, 7, tzinfo=UTC),
        )

        assert occurrence == datetime(2025, 7, 15, 18, 0, tzinfo=UTC)

    def test_due_uses_current_occurrence(self, scheduled_configuration: LoadedConfiguration) -> None:
        """Select only an automation due at the supplied instant."""

        targets = resolve_targets(scheduled_configuration, "owner/repository")
        due = due_automations(targets, datetime(2025, 7, 15, 18, 0, tzinfo=UTC))

        assert len(due) == 1
        assert due[0].name == "scheduled"
        assert due[0].scheduled_for == datetime(2025, 7, 15, 18, 0, tzinfo=UTC)

    def test_missed_occurrences_are_not_due(self, scheduled_configuration: LoadedConfiguration) -> None:
        """Do not catch up a missed automation occurrence."""

        targets = resolve_targets(scheduled_configuration, "owner/repository")

        assert due_automations(targets, datetime(2025, 7, 15, 18, 1, tzinfo=UTC)) == []
