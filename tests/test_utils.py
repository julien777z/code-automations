from datetime import UTC, datetime

import pytest

from cloud_automations.errors import ConfigurationError
from cloud_automations.utils import parse_datetime


class TestParseDatetime:
    """Test ISO timestamp parsing utilities."""

    def test_defaults_to_the_current_utc_instant(self) -> None:
        """Return a timezone-aware UTC timestamp when no value is supplied."""

        before = datetime.now(UTC)
        parsed = parse_datetime(None)
        after = datetime.now(UTC)

        assert before <= parsed <= after

    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            ("2025-07-15T18:25:00+00:00", datetime(2025, 7, 15, 18, 25, tzinfo=UTC)),
            ("2025-07-15T18:25:00Z", datetime(2025, 7, 15, 18, 25, tzinfo=UTC)),
            ("2025-07-15T11:25:00-07:00", datetime(2025, 7, 15, 18, 25, tzinfo=UTC)),
        ],
    )
    def test_parses_timezone_aware_timestamps(self, value: str, expected: datetime) -> None:
        """Parse offset and Z-suffixed timestamps."""

        assert parse_datetime(value) == expected

    def test_rejects_naive_timestamps(self) -> None:
        """Reject timestamps that omit a timezone offset."""

        with pytest.raises(ConfigurationError, match="timestamps must include a timezone offset"):
            parse_datetime("2025-07-15T18:25:00")
