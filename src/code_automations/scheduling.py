import logging
from datetime import UTC, datetime, timedelta
from typing import Final
from zoneinfo import ZoneInfo

from croniter import croniter

from code_automations.models.configuration import AutomationTarget, ScheduleConfig
from code_automations.models.dispatching import AutomationState, DueAutomation

logger = logging.getLogger(__name__)

__all__: Final[tuple[str, ...]] = ("due_automations", "latest_occurrence")


def local_occurrence_to_utc(occurrence: datetime, timezone: ZoneInfo) -> datetime | None:
    """Return a valid local occurrence as a UTC instant."""

    localized = occurrence.replace(tzinfo=timezone, fold=0)

    if localized.astimezone(UTC).astimezone(timezone).replace(tzinfo=None) != occurrence:
        return None

    return localized.astimezone(UTC)


def latest_occurrence(schedule: ScheduleConfig, now: datetime) -> datetime:
    """Return the latest cron occurrence at or before an aware instant."""

    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")

    timezone = ZoneInfo(schedule.timezone)
    current = now.astimezone(UTC)
    local_now = current.astimezone(timezone).replace(tzinfo=None)

    iterator = croniter(schedule.cron, local_now + timedelta(seconds=1))
    previous = iterator.get_prev(datetime)

    while (previous_instant := local_occurrence_to_utc(previous, timezone)) is None:
        previous = iterator.get_prev(datetime)

    next_occurrence = croniter(schedule.cron, local_now).get_next(datetime)
    next_instant = local_occurrence_to_utc(next_occurrence, timezone)

    if next_instant is not None and next_instant <= current:
        return max(previous_instant, next_instant)

    return previous_instant


def due_automations(
    automation_targets: list[AutomationTarget], state: AutomationState, now: datetime
) -> list[DueAutomation]:
    """Find latest missed occurrences within the 24-hour catch-up window."""

    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")

    current = now.astimezone(UTC)
    window_start = current - timedelta(hours=24)
    due: list[DueAutomation] = []

    for target in automation_targets:
        schedule = target.automation.schedule

        if schedule is None or not target.automation.enabled:
            continue

        occurrence = latest_occurrence(schedule, current)
        successful = state.successful.get(target.name)
        since = max(window_start, successful.astimezone(UTC)) if successful is not None else window_start

        if occurrence > since:
            due.append(DueAutomation(target=target, scheduled_for=occurrence))

    return due
