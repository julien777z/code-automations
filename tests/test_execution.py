from pathlib import Path

import pytest

from code_automations.errors import DispatchError
from code_automations.execution import run_automation, validate_agent_result
from code_automations.models.execution import (
    AgentResult,
    AutomationWorkspace,
    PullRequestMetadata,
    RepositoryWorkspace,
)
from code_automations.models.processes import CommandRequest
from code_automations.models.runtime import DispatchRuntime


class TestExecution:
    """Test local Codex execution boundaries."""

    def test_codex_receives_all_repositories_without_the_github_token(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """Pass additional directories while excluding publication credentials."""

        workspace = AutomationWorkspace(
            root=tmp_path,
            home=tmp_path / "home",
            branch="automation/hello-world/run-123",
            repositories=[
                RepositoryWorkspace(
                    repository="owner/primary",
                    branch="main",
                    path=tmp_path / "primary",
                    starting_commit="primary",
                    existing_branch=False,
                ),
                RepositoryWorkspace(
                    repository="owner/secondary",
                    branch="develop",
                    path=tmp_path / "secondary",
                    starting_commit="secondary",
                    existing_branch=False,
                ),
            ],
        )
        runtime = DispatchRuntime(
            github_token="private-token",
            command_path="/usr/bin",
            github_home=tmp_path / "github-home",
            codex_home=tmp_path / "auth",
            runner_temp=tmp_path,
            github_run_id="123",
        )

        def run(request: CommandRequest) -> str:
            """Capture the Codex request and write its structured result."""

            assert request.command[:7] == [
                "codex",
                "exec",
                "--ephemeral",
                "--ignore-user-config",
                "--sandbox",
                "workspace-write",
                "-C",
            ]
            assert "--add-dir" in request.command
            assert str(tmp_path / "secondary") in request.command
            assert "GH_TOKEN" not in request.environment
            assert "private-token" not in request.environment.values()

            output_index = request.command.index("--output-last-message") + 1
            Path(request.command[output_index]).write_text(
                '{"summary":"Completed.","repositories":[]}',
                encoding="utf-8",
            )

            return ""

        monkeypatch.setattr("code_automations.execution.run_command", run)

        result = run_automation(workspace, runtime, "Run the automation.")

        assert result.summary == "Completed."

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
