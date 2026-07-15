from datetime import datetime
from typing import Final

from pydantic import BaseModel, ConfigDict

from cloud_automations.models.configuration import AutomationTarget

__all__: Final[tuple[str, ...]] = ("DueAutomation",)


class DueAutomation(BaseModel):
    """Describe one due scheduled automation."""

    model_config = ConfigDict(frozen=True)

    target: AutomationTarget
    scheduled_for: datetime
