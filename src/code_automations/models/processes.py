from pathlib import Path
from typing import Final

from pydantic import BaseModel, ConfigDict

__all__: Final[tuple[str, ...]] = ("CommandRequest",)


class CommandRequest(BaseModel):
    """Describe one external command execution."""

    model_config = ConfigDict(frozen=True)

    command: list[str]
    cwd: Path
    environment: dict[str, str]
    input_text: str | None = None
