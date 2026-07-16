import logging
import tempfile
from pathlib import Path
from typing import Final

from code_automations.errors import DispatchError
from code_automations.models.execution import (
    AgentResult,
    AutomationWorkspace,
    PublishedPullRequest,
    PullRequestMetadata,
    RepositoryWorkspace,
)
from code_automations.models.processes import CommandEnvironment, CommandRequest
from code_automations.models.runtime import DispatchRuntime
from code_automations.processes import run_command
from code_automations.workspace import (
    GIT_CREDENTIAL_OPTIONS,
    github_environment,
    prepare_branch,
    verify_origin,
    workspace_environment,
)

logger = logging.getLogger(__name__)

__all__: Final[tuple[str, ...]] = ("changed_repositories", "publish_pull_requests")


def changed_repositories(
    workspace: AutomationWorkspace,
    runtime: DispatchRuntime,
) -> list[RepositoryWorkspace]:
    """Return repositories changed without agent-created commits."""

    environment = workspace_environment(workspace, runtime)
    changed: list[RepositoryWorkspace] = []

    for repository in workspace.repositories:
        verify_origin(repository, environment)
        current_commit = run_command(
            CommandRequest(
                command=["git", "rev-parse", "HEAD"],
                cwd=repository.path,
                environment=environment,
            )
        ).strip()

        if current_commit != repository.starting_commit:
            raise DispatchError(f"Codex created a commit in {repository.repository}")

        status = run_command(
            CommandRequest(
                command=["git", "status", "--porcelain"],
                cwd=repository.path,
                environment=environment,
            )
        )

        if status.strip():
            changed.append(repository)

    return changed


def publish_pull_requests(
    workspace: AutomationWorkspace,
    runtime: DispatchRuntime,
    result: AgentResult,
    changed: list[RepositoryWorkspace],
) -> list[PublishedPullRequest]:
    """Commit, push, and create pull requests for changed repositories."""

    if not changed:
        return []

    metadata = {item.repository: item for item in result.repositories}
    environment = workspace_environment(workspace, runtime)
    github = github_environment(runtime)
    publication_root = Path(tempfile.mkdtemp(prefix="publication-", dir=runtime.runner_temp))
    publication_repositories: list[RepositoryWorkspace] = []
    pull_requests: list[PublishedPullRequest] = []

    for repository in changed:
        repository_metadata = metadata[repository.repository]

        commit_repository(repository, repository_metadata, environment)

        patch_path = create_patch(publication_root, repository, environment)
        publication_repository = create_publication_repository(
            publication_root,
            workspace,
            runtime,
            repository,
        )

        apply_patch(publication_repository, patch_path, environment)

        commit_repository(publication_repository, repository_metadata, environment)

        run_command(
            CommandRequest(
                command=[
                    "git",
                    "-c",
                    "core.hooksPath=/dev/null",
                    *GIT_CREDENTIAL_OPTIONS,
                    "push",
                    f"https://github.com/{repository.repository}.git",
                    f"HEAD:refs/heads/{workspace.branch}",
                ],
                cwd=publication_repository.path,
                environment=github,
            )
        )

        publication_repositories.append(publication_repository)

    for repository in publication_repositories:
        pull_requests.append(
            publish_pull_request(
                publication_root,
                workspace,
                repository,
                metadata[repository.repository],
                github,
            )
        )

    return pull_requests


def create_patch(
    publication_root: Path,
    repository: RepositoryWorkspace,
    environment: CommandEnvironment,
) -> Path:
    """Write the committed agent changes as an uncredentialed Git patch."""

    patch = run_command(
        CommandRequest(
            command=["git", "diff", "--binary", repository.starting_commit, "HEAD"],
            cwd=repository.path,
            environment=environment,
        )
    )
    patch_path = publication_root / f"{repository.repository.replace('/', '--')}.patch"
    patch_path.write_text(patch, encoding="utf-8")

    return patch_path


def create_publication_repository(
    publication_root: Path,
    workspace: AutomationWorkspace,
    runtime: DispatchRuntime,
    repository: RepositoryWorkspace,
) -> RepositoryWorkspace:
    """Clone a clean checkout for credentialed publication."""

    path = publication_root / repository.repository.replace("/", "--")
    environment = github_environment(runtime)

    run_command(
        CommandRequest(
            command=[
                "git",
                *GIT_CREDENTIAL_OPTIONS,
                "clone",
                "--branch",
                repository.branch,
                "--single-branch",
                f"https://github.com/{repository.repository}.git",
                str(path),
            ],
            cwd=publication_root,
            environment=environment,
        )
    )

    prepare_branch(path, repository.branch, workspace.branch, environment)

    starting_commit = run_command(
        CommandRequest(
            command=["git", "rev-parse", "HEAD"],
            cwd=path,
            environment=environment,
        )
    ).strip()

    if starting_commit != repository.starting_commit:
        raise DispatchError(f"base branch changed before publication for {repository.repository}")

    return repository.model_copy(update={"path": path})


def apply_patch(
    repository: RepositoryWorkspace,
    patch_path: Path,
    environment: CommandEnvironment,
) -> None:
    """Apply one uncredentialed agent patch to a clean publication checkout."""

    run_command(
        CommandRequest(
            command=["git", "-c", "core.hooksPath=/dev/null", "apply", "--index", str(patch_path)],
            cwd=repository.path,
            environment=environment,
        )
    )


def commit_repository(
    repository: RepositoryWorkspace,
    metadata: PullRequestMetadata,
    environment: CommandEnvironment,
) -> None:
    """Commit all changes for one repository."""

    run_command(
        CommandRequest(
            command=["git", "-c", "core.hooksPath=/dev/null", "add", "--all"],
            cwd=repository.path,
            environment=environment,
        )
    )

    run_command(
        CommandRequest(
            command=["git", "-c", "core.hooksPath=/dev/null", "commit", "--no-verify", "-m", metadata.title],
            cwd=repository.path,
            environment=environment,
        )
    )


def publish_pull_request(
    publication_root: Path,
    workspace: AutomationWorkspace,
    repository: RepositoryWorkspace,
    metadata: PullRequestMetadata,
    environment: CommandEnvironment,
) -> PublishedPullRequest:
    """Create one pull request for a pushed automation branch."""

    body_path = publication_root / f"{repository.repository.replace('/', '--')}.md"
    body_path.write_text(f"{metadata.body.rstrip()}\n\nGenerated by Code Automations.\n", encoding="utf-8")

    output = run_command(
        CommandRequest(
            command=[
                "gh",
                "pr",
                "create",
                "--repo",
                repository.repository,
                "--base",
                repository.branch,
                "--head",
                workspace.branch,
                "--title",
                metadata.title,
                "--body-file",
                str(body_path),
            ],
            cwd=repository.path,
            environment=environment,
        )
    ).strip()

    return PublishedPullRequest(repository=repository.repository, url=output)
