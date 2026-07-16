import logging
from pathlib import Path
from typing import Final, NotRequired, TypedDict

from pydantic import BaseModel, ConfigDict

logger = logging.getLogger(__name__)

__all__: Final[tuple[str, ...]] = ("CommandEnvironment", "CommandRequest")


class CommandEnvironment(TypedDict):
    """Define the explicit environment for one external command."""

    HOME: str
    PATH: str
    GH_TOKEN: NotRequired[str]
    GIT_CONFIG_GLOBAL: NotRequired[str]
    GIT_CONFIG_NOSYSTEM: NotRequired[str]


class CommandRequest(BaseModel):
    """Describe one external command execution."""

    model_config = ConfigDict(frozen=True)

    command: list[str]
    cwd: Path
    environment: CommandEnvironment
    input_text: str | None = None
