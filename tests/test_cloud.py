import subprocess
from datetime import timedelta

import pytest

from code_automations.cloud import submit_cloud_task, wait_for_cloud_task
from code_automations.errors import DispatchError
from code_automations.models.runtime import CloudTask


class TestCloud:
    """Test Codex Cloud submission and monitoring."""

    def test_submit_cloud_task_returns_task_identity(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Parse the exact task URL returned by Codex."""

        def run(*args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
            """Return one accepted Cloud task."""

            return subprocess.CompletedProcess(
                args=[],
                returncode=0,
                stdout="https://chatgpt.com/codex/tasks/task_example\n",
                stderr="",
            )

        monkeypatch.setattr("code_automations.cloud.subprocess.run", run)

        task = submit_cloud_task("environment_example", "main", "Run automation")

        assert task.task_id == "task_example"
        assert str(task.url) == "https://chatgpt.com/codex/tasks/task_example"

    def test_submit_cloud_task_rejects_invalid_output(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Reject output that is not a task URL."""

        monkeypatch.setattr(
            "code_automations.cloud.subprocess.run",
            lambda *args, **kwargs: subprocess.CompletedProcess(
                args=[],
                returncode=0,
                stdout="accepted",
                stderr="",
            ),
        )

        with pytest.raises(DispatchError, match="did not return a task URL"):
            submit_cloud_task("environment_example", "main", "Run automation")

    def test_wait_for_cloud_task_reaches_ready(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Poll pending work until Codex reports completion."""

        statuses = iter(
            [
                subprocess.CompletedProcess(
                    args=[],
                    returncode=1,
                    stdout="[PENDING] Working",
                    stderr="",
                ),
                subprocess.CompletedProcess(
                    args=[],
                    returncode=0,
                    stdout="[READY] Complete",
                    stderr="",
                ),
            ]
        )

        monkeypatch.setattr(
            "code_automations.cloud.subprocess.run",
            lambda *args, **kwargs: next(statuses),
        )
        monkeypatch.setattr("code_automations.cloud.time.sleep", lambda seconds: None)

        wait_for_cloud_task(
            CloudTask(
                task_id="task_example",
                url="https://chatgpt.com/codex/tasks/task_example",
            ),
            timedelta(minutes=1),
        )

    def test_wait_for_cloud_task_reports_failure(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Fail when Codex reports an error state."""

        monkeypatch.setattr(
            "code_automations.cloud.subprocess.run",
            lambda *args, **kwargs: subprocess.CompletedProcess(
                args=[],
                returncode=0,
                stdout="[ERROR] Failed",
                stderr="",
            ),
        )

        with pytest.raises(DispatchError, match="Cloud task failed"):
            wait_for_cloud_task(
                CloudTask(
                    task_id="task_example",
                    url="https://chatgpt.com/codex/tasks/task_example",
                ),
                timedelta(minutes=1),
            )
