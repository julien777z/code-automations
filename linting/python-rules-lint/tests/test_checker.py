import subprocess
import sys
from pathlib import Path
from typing import Final

import pytest

type ReportedMessage = tuple[str, int]

CUSTOM_MESSAGES: Final[str] = ",".join(
    (
        "banned-python-terminology",
        "direct-environment-read",
        "forbidden-module-docstring",
        "forbidden-opening-comment",
        "forbidden-python-construct",
        "invalid-leading-underscore",
        "missing-blank-line-after-docstring",
        "missing-definition-docstring",
        "model-outside-models-directory",
        "multiline-definition-docstring",
        "parent-relative-import",
        "uppercase-logger-name",
    )
)


def run_pylint(path: Path, *, use_root_config: bool = False) -> subprocess.CompletedProcess[str]:
    """Run Pylint with the shared checker against one path."""

    command = [
        sys.executable,
        "-m",
        "pylint",
        "--load-plugins=python_rules_lint",
        "--msg-template={symbol}:{line}",
    ]

    if use_root_config:
        command.append("--rcfile=pyproject.toml")
    else:
        command.extend(("--disable=all", f"--enable={CUSTOM_MESSAGES}"))

    command.append(str(path))

    return subprocess.run(command, check=False, capture_output=True, text=True)


def reported_messages(result: subprocess.CompletedProcess[str]) -> set[ReportedMessage]:
    """Parse stable message symbols and line numbers from Pylint output."""

    messages: set[ReportedMessage] = set()

    for line in result.stdout.splitlines():
        symbol, separator, line_number = line.partition(":")

        if separator and line_number.isdigit():
            messages.add((symbol, int(line_number)))

    return messages


@pytest.fixture
def invalid_source(tmp_path: Path) -> Path:
    """Create source that exercises every custom diagnostic."""

    source_path = tmp_path / "invalid.py"
    source_path.write_text(
        '''# best effort setup
"""Module documentation."""
from ..parent import value
from typing import Any, Protocol, cast
from dataclasses import dataclass
import os

_module_value = 1

class _Hidden:
    """Describe the hidden class."""

def missing_docstring():
    return None

def multiline_docstring():
    """Describe the function
    across multiple lines.
    """

    return None

def compact_docstring():
    """Describe the function."""
    return None

def create_seed_records():
    """Create sample records."""

    value = os.getenv("VALUE")
    other = os.environ.get("OTHER")
    print(cast(Any, value), other)

    return dataclass(value)

class Contract(Protocol):
    """Describe the contract."""

''',
        encoding="utf-8",
    )

    return source_path


@pytest.fixture
def valid_package(tmp_path: Path) -> Path:
    """Create valid source covering convention exceptions."""

    package = tmp_path / "valid_package"
    package.mkdir()
    models = package / "models"
    models.mkdir()

    (package / "module.py").write_text(
        '''CONSTANT = "value"


def outer() -> str:
    """Return a value from a nested helper."""

    def _inner() -> str:
        """Return the nested value."""

        return CONSTANT

    return _inner()


class Container:
    """Contain a permitted nested class."""

    class _Nested:
        """Represent a nested implementation."""

        def __init__(self) -> None:
            """Initialize the nested implementation."""

''',
        encoding="utf-8",
    )
    (package / "__main__.py").write_text(
        '''from .module import outer


def main() -> str:
    """Return the package result."""

    return outer()
''',
        encoding="utf-8",
    )
    (models / "configuration.py").write_text(
        '''from pydantic import BaseModel


class Configuration(BaseModel):
    """Define valid configuration."""

''',
        encoding="utf-8",
    )

    return package


@pytest.fixture
def invalid_model_source(tmp_path: Path) -> Path:
    """Create source with misplaced model and logger declarations."""

    source_path = tmp_path / "runtime.py"
    source_path.write_text(
        '''import logging
from pydantic import BaseModel

LOGGER = logging.getLogger(__name__)


class Request(BaseModel):
    """Define a request."""

''',
        encoding="utf-8",
    )

    return source_path


class TestPythonRulesChecker:
    """Verify the shared checker through Pylint's public interface."""

    def test_reports_every_custom_diagnostic(self, invalid_source: Path) -> None:
        """Report stable symbols and locations for every custom rule."""

        result = run_pylint(invalid_source)
        messages = reported_messages(result)

        assert ("astroid-error", 1) not in messages, result.stdout + result.stderr
        assert result.returncode != 0
        assert ("forbidden-opening-comment", 1) in messages
        assert ("banned-python-terminology", 1) in messages
        assert ("forbidden-module-docstring", 2) in messages
        assert ("parent-relative-import", 3) in messages
        assert ("forbidden-python-construct", 4) in messages
        assert ("forbidden-python-construct", 5) in messages
        assert ("invalid-leading-underscore", 8) in messages
        assert ("invalid-leading-underscore", 10) in messages
        assert ("missing-definition-docstring", 13) in messages
        assert ("multiline-definition-docstring", 16) in messages
        assert ("missing-blank-line-after-docstring", 23) in messages
        assert ("banned-python-terminology", 27) in messages
        assert ("direct-environment-read", 30) in messages
        assert ("direct-environment-read", 31) in messages

    def test_accepts_supported_exceptions(self, valid_package: Path) -> None:
        """Accept nested definitions, dunders, and entrypoint imports."""

        result = run_pylint(valid_package)

        assert result.returncode == 0, result.stdout + result.stderr
        assert reported_messages(result) == set()

    def test_reports_model_and_logger_placement(self, invalid_model_source: Path) -> None:
        """Report misplaced models and constant-style logger names."""

        result = run_pylint(invalid_model_source)
        messages = reported_messages(result)

        assert ("uppercase-logger-name", 4) in messages
        assert ("model-outside-models-directory", 7) in messages

    def test_loads_from_root_configuration(self, valid_package: Path) -> None:
        """Load the plugin and allowlist from the consumer configuration."""

        result = run_pylint(valid_package, use_root_config=True)

        assert result.returncode == 0, result.stdout + result.stderr
