from typing import Final

__all__: Final[tuple[str, ...]] = ("ConfigurationError", "DispatchError")


class ConfigurationError(ValueError):
    """Report invalid automation configuration."""

    pass


class DispatchError(RuntimeError):
    """Report a failed Codex Cloud submission."""

    pass
