from pathlib import Path

import pytest

from code_automations.errors import DispatchError
from code_automations.execution import container_repositories, run_automation, validate_agent_result
from code_automations.models.execution import (
    AgentResult,
    AutomationWorkspace,
    PullRequestMetadata,
    RepositoryWorkspace,
)
from code_automations.models.processes import CommandRequest
from code_automations.models.runtime import DispatchRuntime


class TestExecution:
    """Test Docker-isolated Codex execution boundaries."""

    def test_codex_receives_only_container_workspaces_and_authentication(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """Harden the container while excluding runner publication credentials."""

        root = tmp_path / "workspace"
        root.mkdir()
        (root / "home").mkdir()

        workspace = AutomationWorkspace(
            root=root,
            home=root / "home",
            branch="automation/hello-world/run-123",
            repositories=[
                RepositoryWorkspace(
                    repository="owner/primary",
                    branch="main",
                    path=root / "primary",
                    starting_commit="primary",
                ),
                RepositoryWorkspace(
                    repository="owner/secondary",
                    branch="develop",
                    path=root / "secondary",
                    starting_commit="secondary",
                ),
            ],
        )

        runtime = DispatchRuntime(
            github_token="private-token",
            command_path="/usr/bin",
            github_home=tmp_path / "github-home",
            codex_home=tmp_path / "auth",
            runner_image="code-automations-runner:123",
            runner_user="1001:1001",
            runner_temp=tmp_path,
            github_run_id="123",
            github_run_attempt="1",
        )

        def run(request: CommandRequest) -> str:
            """Capture the Docker request and write its structured result."""

            assert request.command[:3] == ["docker", "run", "--rm"]
            assert "--cap-drop=ALL" in request.command
            assert "--security-opt=no-new-privileges" in request.command
            assert "--read-only" in request.command
            assert "--pids-limit=256" in request.command
            assert "--network=bridge" in request.command
            assert "--pid=host" not in request.command
            assert "/var/run/docker.sock" not in " ".join(request.command)
            assert request.command.count("--mount") == 2
            assert f"type=bind,source={root},target=/workspace" in request.command
            assert f"type=bind,source={tmp_path / 'auth'},target=/codex-home" in request.command
            assert str(tmp_path / "github-home") not in " ".join(request.command)
            assert request.command[request.command.index("-C") + 1] == "/workspace/primary"
            assert request.command[request.command.index("--add-dir") + 1] == "/workspace/secondary"
            assert (
                request.command[request.command.index("--output-schema") + 1]
                == "/workspace/result.schema.json"
            )

            assert (
                request.command[request.command.index("--output-last-message") + 1]
                == "/workspace/result.json"
            )

            assert "GH_TOKEN" not in request.environment
            assert "private-token" not in request.environment.values()
            assert "private-token" not in " ".join(request.command)
            assert request.input_text == "Run the automation."

            (root / "result.json").write_text(
                '{"summary":"Completed.","repositories":[]}',
                encoding="utf-8",
            )

            return ""

        monkeypatch.setattr("code_automations.execution.run_command", run)

        result = run_automation(workspace, runtime, "Run the automation.")

        assert result.summary == "Completed."

        assert [repository.path for repository in container_repositories(workspace)] == [
            Path("/workspace/primary"),
            Path("/workspace/secondary"),
        ]

    def test_result_metadata_must_match_changed_repositories(self) -> None:
        """Reject missing, duplicate, and unexpected pull request metadata."""

        result = AgentResult(
            summary="Completed.",
            repositories=[
                PullRequestMetadata(repository="owner/primary", title="Change", body="Summary"),
            ],
        )

        with pytest.raises(DispatchError, match="exactly match"):
            validate_agent_result(result, ["owner/secondary"])

        duplicate = AgentResult(
            summary="Completed.",
            repositories=[
                PullRequestMetadata(repository="owner/primary", title="One", body="Summary"),
                PullRequestMetadata(repository="owner/primary", title="Two", body="Summary"),
            ],
        )

        with pytest.raises(DispatchError, match="duplicate"):
            validate_agent_result(duplicate, ["owner/primary"])
