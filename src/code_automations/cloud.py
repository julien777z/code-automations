import logging
import re
import subprocess
import time
from datetime import timedelta
from enum import StrEnum
from typing import Final

from code_automations.errors import DispatchError
from code_automations.models.runtime import CloudTask

logger = logging.getLogger(__name__)

TASK_URL_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"https://chatgpt\.com/codex/tasks/(?P<task_id>[A-Za-z0-9_-]+)"
)
TASK_STATUS_PATTERN: Final[re.Pattern[str]] = re.compile(r"^\[(?P<status>[A-Z]+)]")
POLL_INTERVAL: Final[timedelta] = timedelta(seconds=15)

__all__: Final[tuple[str, ...]] = ("submit_cloud_task", "wait_for_cloud_task")


class CloudTaskStatus(StrEnum):
    """Name a Codex Cloud task lifecycle state."""

    APPLIED = "APPLIED"
    ERROR = "ERROR"
    PENDING = "PENDING"
    READY = "READY"


def run_codex(command: list[str]) -> str:
    """Run one Codex Cloud command and return its output."""

    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as error:
        raise DispatchError(f"unable to start Codex: {error}") from error

    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or "Codex command failed"

        raise DispatchError(detail)

    return result.stdout.strip()


def submit_cloud_task(environment: str, branch: str, prompt: str) -> CloudTask:
    """Submit one coordinating Codex Cloud task."""

    output = run_codex(
        [
            "codex",
            "cloud",
            "exec",
            "--env",
            environment,
            "--attempts",
            "1",
            "--branch",
            branch,
            prompt,
        ]
    )
    match = TASK_URL_PATTERN.fullmatch(output)

    if match is None:
        raise DispatchError("codex cloud exec did not return a task URL")

    return CloudTask(task_id=match.group("task_id"), url=output)


def cloud_task_status(task: CloudTask) -> CloudTaskStatus:
    """Read one Codex Cloud task status."""

    output = run_codex(["codex", "cloud", "status", task.task_id])
    match = TASK_STATUS_PATTERN.match(output)

    if match is None:
        raise DispatchError("codex cloud status did not return a recognized status")

    try:
        return CloudTaskStatus(match.group("status"))
    except ValueError as error:
        raise DispatchError(f"unsupported Codex Cloud task status: {match.group('status')}") from error


def wait_for_cloud_task(task: CloudTask, timeout: timedelta) -> None:
    """Wait for one Codex Cloud task to finish."""

    started_at = time.monotonic()

    while True:
        status = cloud_task_status(task)

        logger.info("%s: %s", task.url, status.value.lower())

        match status:
            case CloudTaskStatus.READY | CloudTaskStatus.APPLIED:
                return
            case CloudTaskStatus.ERROR:
                raise DispatchError(f"Codex Cloud task failed: {task.url}")
            case CloudTaskStatus.PENDING:
                if time.monotonic() - started_at >= timeout.total_seconds():
                    raise DispatchError(f"Codex Cloud task timed out: {task.url}")

                time.sleep(POLL_INTERVAL.total_seconds())
