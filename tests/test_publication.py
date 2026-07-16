from pathlib import Path

import pytest

from code_automations.models.execution import (
    AgentResult,
    AutomationWorkspace,
    ExistingPullRequest,
    PublishedPullRequest,
    PullRequestMetadata,
    RepositoryWorkspace,
)
from code_automations.models.processes import CommandEnvironment, CommandRequest
from code_automations.models.runtime import DispatchRuntime
from code_automations.publication import (
    existing_pull_request,
    publish_pull_requests,
    recovery_metadata,
    recovery_repositories,
)
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

    def test_pull_request_lookup_ignores_matching_branches_from_forks(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """Select the configured repository's pull request for a shared branch name."""

        repository = RepositoryWorkspace(
            repository="owner/repository",
            branch="main",
            path=tmp_path,
            starting_commit="commit",
            existing_branch=True,
        )
        environment = CommandEnvironment(HOME=str(tmp_path), PATH="/bin")

        def run(request: CommandRequest) -> str:
            """Return pull requests from the configured repository and a fork."""

            assert request.command == [
                "gh",
                "pr",
                "list",
                "--repo",
                "owner/repository",
                "--head",
                "automation/review/run-123",
                "--state",
                "all",
                "--limit",
                "1000",
                "--json",
                "url,state,headRepository,headRepositoryOwner",
            ]

            return """[
  {
    "url": "https://github.com/owner/repository/pull/1",
    "state": "OPEN",
    "headRepository": {"name": "repository"},
    "headRepositoryOwner": {"login": "owner"}
  },
  {
    "url": "https://github.com/fork/repository/pull/2",
    "state": "OPEN",
    "headRepository": {"name": "repository"},
    "headRepositoryOwner": {"login": "fork"}
  }
]"""

        monkeypatch.setattr("code_automations.publication.run_command", run)

        pull_request = existing_pull_request(repository, "automation/review/run-123", environment)

        assert pull_request is not None
        assert str(pull_request.url) == "https://github.com/owner/repository/pull/1"

    def test_publication_pushes_from_the_clean_checkout(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        """Keep GitHub credentials out of the agent-owned checkout."""

        repository = RepositoryWorkspace(
            repository="owner/repository",
            branch="main",
            path=tmp_path / "agent",
            starting_commit="commit",
            existing_branch=False,
        )
        workspace = AutomationWorkspace(
            root=tmp_path,
            home=tmp_path / "home",
            branch="automation/review/run-123",
            repositories=[repository],
        )
        runtime = DispatchRuntime(
            github_token="token",
            command_path="/bin",
            github_home=tmp_path / "github-home",
            codex_home=tmp_path / "codex-home",
            runner_temp=tmp_path,
            github_run_id="123",
        )
        result = AgentResult(
            summary="Completed.",
            repositories=[
                PullRequestMetadata(
                    repository="owner/repository",
                    title="Update repository",
                    body="Summary",
                )
            ],
        )
        clean_repository = repository.model_copy(update={"path": tmp_path / "publication"})
        commands: list[CommandRequest] = []

        def commit(
            received_repository: RepositoryWorkspace,
            metadata: PullRequestMetadata,
            environment: CommandEnvironment,
        ) -> None:
            """Require uncredentialed commits in both workspaces."""

            assert received_repository in (repository, clean_repository)
            assert metadata.repository == repository.repository
            assert "GH_TOKEN" not in environment

        def create_patch(
            received_workspace: AutomationWorkspace,
            received_repository: RepositoryWorkspace,
            environment: CommandEnvironment,
        ) -> Path:
            """Return an uncredentialed patch path."""

            assert received_workspace is workspace
            assert received_repository is repository
            assert "GH_TOKEN" not in environment

            return tmp_path / "changes.patch"

        def create_checkout(
            received_workspace: AutomationWorkspace,
            received_runtime: DispatchRuntime,
            received_repository: RepositoryWorkspace,
        ) -> RepositoryWorkspace:
            """Return the trusted publication checkout."""

            assert received_workspace is workspace
            assert received_runtime is runtime
            assert received_repository is repository

            return clean_repository

        def apply(
            received_repository: RepositoryWorkspace,
            patch_path: Path,
            environment: CommandEnvironment,
        ) -> None:
            """Require uncredentialed patch application in the clean checkout."""

            assert received_repository is clean_repository
            assert patch_path == tmp_path / "changes.patch"
            assert "GH_TOKEN" not in environment

        def run(request: CommandRequest) -> str:
            """Capture the authenticated push command."""

            commands.append(request)

            return ""

        def publish(
            received_workspace: AutomationWorkspace,
            received_repository: RepositoryWorkspace,
            metadata: PullRequestMetadata,
            environment: CommandEnvironment,
        ) -> PublishedPullRequest:
            """Publish through the clean checkout."""

            assert received_workspace is workspace
            assert received_repository is clean_repository
            assert metadata.repository == repository.repository
            assert environment["GH_TOKEN"] == "token"

            return PublishedPullRequest(
                repository=repository.repository,
                url="https://github.com/owner/repository/pull/1",
            )

        def recover(
            received_workspace: AutomationWorkspace,
            changed: list[RepositoryWorkspace],
            environment: CommandEnvironment,
        ) -> list[RepositoryWorkspace]:
            """Report no previously pushed branches for this test."""

            assert received_workspace is workspace
            assert changed == [repository]
            assert environment["GH_TOKEN"] == "token"

            return []

        monkeypatch.setattr("code_automations.publication.commit_repository", commit)
        monkeypatch.setattr("code_automations.publication.create_patch", create_patch)
        monkeypatch.setattr("code_automations.publication.create_publication_repository", create_checkout)
        monkeypatch.setattr("code_automations.publication.apply_patch", apply)
        monkeypatch.setattr("code_automations.publication.recovery_repositories", recover)
        monkeypatch.setattr("code_automations.publication.run_command", run)
        monkeypatch.setattr("code_automations.publication.publish_pull_request", publish)

        pull_requests = publish_pull_requests(workspace, runtime, result, [repository])

        assert pull_requests[0].repository == repository.repository
        assert commands[0].cwd == clean_repository.path
        assert commands[0].environment["GH_TOKEN"] == "token"
