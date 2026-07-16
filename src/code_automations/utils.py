from datetime import UTC, datetime
from typing import Final

from code_automations.errors import ConfigurationError

__all__: Final[tuple[str, ...]] = ("parse_datetime",)


def parse_datetime(value: str | None) -> datetime:
    """Parse an aware ISO timestamp or return the current UTC instant."""

    if value is None:
        return datetime.now(UTC)

    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))

    if parsed.tzinfo is None:
        raise ConfigurationError("timestamps must include a timezone offset")

    return parsed
