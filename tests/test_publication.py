from pathlib import Path

import pytest

from code_automations.models.execution import (
    AutomationWorkspace,
    ExistingPullRequest,
    RepositoryWorkspace,
)
from code_automations.models.processes import CommandEnvironment, CommandRequest
from code_automations.publication import recovery_metadata, recovery_repositories
from code_automations.workspace import GIT_CREDENTIAL_OPTIONS, prepare_branch


class TestPublication:
    """Test retry-safe branch restoration and publication recovery."""

    def test_existing_branch_fetches_a_remote_tracking_ref(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """Restore a retry branch through an explicit remote-tracking refspec."""

        requests: list[CommandRequest] = []
        environment = CommandEnvironment(HOME=str(tmp_path), PATH="/bin")

        def run(request: CommandRequest) -> str:
            """Capture branch preparation commands."""

            requests.append(request)

            if "ls-remote" in request.command:
                return "commit\trefs/heads/automation/review/run-123\n"

            return ""

        monkeypatch.setattr("code_automations.workspace.run_command", run)

        existing = prepare_branch(
            tmp_path,
            "main",
            "automation/review/run-123",
            environment,
        )

        fetch = next(request for request in requests if "fetch" in request.command)

        assert existing is True
        assert fetch.command == [
            "git",
            *GIT_CREDENTIAL_OPTIONS,
            "fetch",
            "origin",
            "automation/review/run-123:refs/remotes/origin/automation/review/run-123",
        ]

    def test_recovery_creates_missing_pull_request_for_existing_branch(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """Recover a pushed branch when a prior run did not create its pull request."""

        repository = RepositoryWorkspace(
            repository="owner/repository",
            branch="main",
            path=tmp_path,
            starting_commit="commit",
            existing_branch=True,
        )
        workspace = AutomationWorkspace(
            root=tmp_path,
            home=tmp_path / "home",
            branch="automation/review/run-123",
            repositories=[repository],
        )
        environment = CommandEnvironment(HOME=str(tmp_path), PATH="/bin")

        def find_pull_request(
            received_repository: RepositoryWorkspace,
            output_branch: str,
            received_environment: CommandEnvironment,
        ) -> ExistingPullRequest | None:
            """Report that the pushed branch has no pull request."""

            assert received_repository is repository
            assert output_branch == workspace.branch
            assert received_environment is environment

            return None

        monkeypatch.setattr("code_automations.publication.existing_pull_request", find_pull_request)

        recovered = recovery_repositories(workspace, [], environment)

        assert recovered == [repository]

    def test_recovery_metadata_uses_the_existing_commit_title(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """Build metadata for a branch that was pushed by an earlier run."""

        repository = RepositoryWorkspace(
            repository="owner/repository",
            branch="main",
            path=tmp_path,
            starting_commit="commit",
            existing_branch=True,
        )
        environment = CommandEnvironment(HOME=str(tmp_path), PATH="/bin")

        def run(request: CommandRequest) -> str:
            """Return the prior commit subject."""

            assert request.command == ["git", "log", "-1", "--format=%s"]

            return "Update review rules\n"

        monkeypatch.setattr("code_automations.publication.run_command", run)

        metadata = recovery_metadata(repository, environment)

        assert metadata.title == "Update review rules"
        assert metadata.repository == "owner/repository"
