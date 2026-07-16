import logging
from pathlib import Path
from typing import Final

from pydantic import ValidationError

from code_automations.errors import ConfigurationError
from code_automations.models.dispatching import AutomationState

logger = logging.getLogger(__name__)

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
