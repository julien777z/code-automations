import re
from pathlib import PurePosixPath
from typing import Final, Literal, Self
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from croniter import croniter
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator

__all__: Final[tuple[str, ...]] = (
    "AUTOMATION_PATTERN",
    "AutomationConfig",
    "AutomationState",
    "AutomationsConfig",
    "REPOSITORY_PATTERN",
    "RepositoryConfig",
    "ScheduleConfig",
    "validate_branch",
    "validate_cron_field",
    "validate_reference",
)

REPOSITORY_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"^(?![A-Za-z0-9-]*--)[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?/[A-Za-z0-9._-]{1,100}$"
)
AUTOMATION_PATTERN: Final[re.Pattern[str]] = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
CRON_FIELD_BOUNDS: Final[tuple[tuple[int, int], ...]] = ((0, 59), (0, 23), (1, 31), (1, 12), (0, 7))


def validate_reference(value: str) -> str:
    """Validate a prompt or skill reference."""

    if not value or value.endswith(".md") or "\\" in value or "//" in value or value.endswith("/"):
        raise ValueError("references must omit .md and use forward-slash relative paths")

    path = PurePosixPath(value)

    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError("references must not be absolute or contain traversal segments")

    if any(not AUTOMATION_PATTERN.fullmatch(part) for part in path.parts):
        raise ValueError("reference path segments contain unsupported characters")

    return value


def validate_branch(value: str) -> str:
    """Validate a Git branch name."""

    invalid = (
        not value
        or len(value) > 255
        or value.startswith(("-", ".", "/"))
        or value.endswith((".", "/", ".lock"))
        or value == "@"
        or ".." in value
        or "@{" in value
        or "//" in value
        or "\\" in value
        or any(character.isspace() or ord(character) < 32 or character in "~^:?*[" for character in value)
    )

    if invalid:
        raise ValueError("invalid Git branch name")

    if any(part.startswith(".") or part.endswith(".lock") for part in value.split("/")):
        raise ValueError("invalid Git branch name")

    return value


def validate_cron_field(value: str, minimum: int, maximum: int) -> bool:
    """Validate one numeric POSIX cron field."""

    for entry in value.split(","):
        segments = entry.split("/")

        if len(segments) > 2 or not segments[0]:
            return False

        base = segments[0]
        if len(segments) == 2:
            if not segments[1].isdigit() or int(segments[1]) < 1 or int(segments[1]) > maximum - minimum + 1:
                return False

        if base == "*":
            continue

        bounds = base.split("-")

        if len(bounds) > 2 or any(not bound.isdigit() for bound in bounds):
            return False

        start = int(bounds[0])
        end = int(bounds[-1])

        if start < minimum or end > maximum or start > end:
            return False

    return True


class ScheduleConfig(BaseModel):
    """Define a timezone-aware POSIX cron schedule."""

    model_config = ConfigDict(extra="forbid", strict=True)

    cron: str
    timezone: str

    @field_validator("cron")
    @classmethod
    def validate_cron(cls, value: str) -> str:
        """Require a five-field POSIX cron expression."""

        fields = value.split()

        if (
            len(fields) != 5
            or not all(
                validate_cron_field(field, minimum, maximum)
                for field, (minimum, maximum) in zip(fields, CRON_FIELD_BOUNDS, strict=True)
            )
            or not croniter.is_valid(value)
        ):
            raise ValueError("schedule cron must be a valid five-field POSIX expression")

        return value

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        """Require an available IANA timezone."""

        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as error:
            raise ValueError("schedule timezone must be a valid IANA timezone") from error

        return value


class AutomationConfig(BaseModel):
    """Define one Cloud automation."""

    model_config = ConfigDict(extra="forbid", strict=True)

    prompt: str
    skills: list[str] = Field(default_factory=list)
    attempts: int = Field(default=1, ge=1, le=4)
    schedule: ScheduleConfig | None = None
    enabled: bool = True

    @field_validator("prompt")
    @classmethod
    def validate_prompt(cls, value: str) -> str:
        """Validate the prompt reference."""

        return validate_reference(value)

    @field_validator("skills")
    @classmethod
    def validate_skills(cls, value: list[str]) -> list[str]:
        """Validate ordered skill references."""

        return [validate_reference(reference) for reference in value]


class RepositoryConfig(BaseModel):
    """Group automations for one repository and Cloud environment."""

    model_config = ConfigDict(extra="forbid", strict=True)

    environment: str | None = Field(default=None, min_length=1, max_length=64)
    branch: str = "main"
    automations: dict[str, AutomationConfig] = Field(min_length=1)

    @field_validator("environment")
    @classmethod
    def validate_environment(cls, value: str | None) -> str | None:
        """Validate an optional Cloud environment label."""

        if value is not None and (value != value.strip() or not value.isprintable()):
            raise ValueError("invalid Cloud environment label")

        return value

    @field_validator("branch")
    @classmethod
    def validate_repository_branch(cls, value: str) -> str:
        """Validate the repository branch."""

        return validate_branch(value)

    @field_validator("automations")
    @classmethod
    def validate_automation_names(cls, value: dict[str, AutomationConfig]) -> dict[str, AutomationConfig]:
        """Validate automation names."""

        invalid_name = next((name for name in value if not AUTOMATION_PATTERN.fullmatch(name)), None)

        if invalid_name is not None:
            raise ValueError(f"invalid automation name: {invalid_name}")

        return value


class AutomationsConfig(BaseModel):
    """Define the complete automation configuration."""

    model_config = ConfigDict(extra="forbid", strict=True)

    version: Literal[1]
    repositories: dict[str, RepositoryConfig] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_repositories_and_names(self) -> Self:
        """Validate repository keys and global automation-name uniqueness."""

        automation_names: set[str] = set()

        for repository, config in self.repositories.items():
            if repository != "self" and not REPOSITORY_PATTERN.fullmatch(repository):
                raise ValueError(f"invalid repository identifier: {repository}")

            for name in config.automations:
                if name in automation_names:
                    raise ValueError(f"duplicate automation name: {name}")

                automation_names.add(name)

        return self


class AutomationState(BaseModel):
    """Track successful scheduled submissions."""

    model_config = ConfigDict(extra="forbid", strict=True)

    version: Literal[1] = 1
    successful: dict[str, AwareDatetime] = Field(default_factory=dict)
