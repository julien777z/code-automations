from pathlib import Path
from typing import Final

from pydantic import ValidationError

from cloud_automations.errors import ConfigurationError
from cloud_automations.models.state import AutomationState

__all__: Final[tuple[str, ...]] = ("load_state", "save_state")


def load_state(path: Path | None) -> AutomationState:
    """Load dispatcher state or return an empty state."""

    if path is None or not path.exists():
        return AutomationState()

    try:
        return AutomationState.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValidationError) as error:
        raise ConfigurationError(f"unable to load dispatcher state: {error}") from error


def save_state(path: Path, state: AutomationState) -> None:
    """Persist dispatcher state deterministically."""

    path.write_text(state.model_dump_json(indent=2) + "\n", encoding="utf-8")
