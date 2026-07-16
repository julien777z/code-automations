import subprocess
from typing import Final

from code_automations.errors import DispatchError
from code_automations.models.processes import CommandRequest

__all__: Final[tuple[str, ...]] = ("run_command",)


def run_command(request: CommandRequest) -> str:
    """Run one command and return its standard output."""

    try:
        result = subprocess.run(
            request.command,
            cwd=request.cwd,
            env=request.environment,
            input=request.input_text,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as error:
        raise DispatchError(f"unable to start command: {error}") from error

    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or "command failed without an error message"

        raise DispatchError(detail)

    return result.stdout
