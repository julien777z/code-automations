from typing import Final, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

__all__: Final[tuple[str, ...]] = ("AutomationState",)


class AutomationState(BaseModel):
    """Track successful scheduled submissions."""

    model_config = ConfigDict(extra="forbid", strict=True)

    version: Literal[1] = 1
    successful: dict[str, AwareDatetime] = Field(default_factory=dict)
