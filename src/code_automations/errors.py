import logging
from typing import Final

logger = logging.getLogger(__name__)

__all__: Final[tuple[str, ...]] = ("ConfigurationError", "DispatchError")


class ConfigurationError(ValueError):
    """Report invalid automation configuration."""

    pass


class DispatchError(RuntimeError):
    """Report a failed automation execution or publication."""

    pass
