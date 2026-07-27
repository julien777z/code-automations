from datetime import UTC, datetime
from typing import Final

from code_automations.errors import ConfigurationError

__all__: Final[tuple[str, ...]] = ("parse_datetime",)


def parse_datetime(value: str | None) -> datetime:
    """Parse one timezone-aware timestamp or return the current instant."""

    if value is None:
        return datetime.now(UTC)

    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ConfigurationError(f"invalid timestamp: {value}") from error

    if parsed.tzinfo is None:
        raise ConfigurationError("timestamps must include a timezone offset")

    return parsed.astimezone(UTC)
