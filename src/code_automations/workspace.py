import re
import tempfile
from datetime import UTC
from pathlib import Path
from typing import Final

from code_automations.errors import DispatchError
from code_automations.models.dispatching import ExecutionRequest
from code_automations.models.execution import AutomationWorkspace, RepositoryWorkspace
from code_automations.models.processes import CommandRequest
from code_automations.models.runtime import DispatchRuntime
from code_automations.processes import run_command

__all__: Final[tuple[str, ...]] = (
    "create_workspace",
    "github_environment",
    "output_branch",
    "verify_origin",
)

GIT_AUTHOR_NAME: Final[str] = "github-actions[bot]"
GIT_AUTHOR_EMAIL: Final[str] = "41898282+github-actions[bot]@users.noreply.github.com"
GITHUB_ORIGIN_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"^(?:https://github\.com/|git@github\.com:|ssh://git@github\.com/)([A-Za-z0-9._-]+/[A-Za-z0-9._-]+?)(?:\.git)?$"
)


def github_environment(runtime: DispatchRuntime) -> dict[str, str]:
    """Build the restricted environment for GitHub CLI and Git commands."""

    return {
        "GH_TOKEN": runtime.github_token,
        "HOME": runtime.home,
        "PATH": runtime.command_path,
    }


def output_branch(request: ExecutionRequest, runtime: DispatchRuntime) -> str:
    """Build the deterministic branch for one automation execution."""

    if request.scheduled_for is not None:
        occurrence = request.scheduled_for.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")

        return f"automation/{request.target.name}/{occurrence}"

    return f"automation/{request.target.name}/run-{runtime.github_run_id}"


def create_workspace(request: ExecutionRequest, runtime: DispatchRuntime) -> AutomationWorkspace:
    """Clone and prepare every repository for one automation execution."""

    root = Path(tempfile.mkdtemp(prefix=f"{request.target.name}-", dir=runtime.runner_temp))
    branch = output_branch(request, runtime)
    environment = github_environment(runtime)

    run_command(
        CommandRequest(
            command=["gh", "auth", "setup-git"],
            cwd=root,
            environment=environment,
        )
    )

    repositories: list[RepositoryWorkspace] = []

    for index, repository in enumerate(request.target.repositories, start=1):
        path = root / f"{index}-{repository.repository.replace('/', '--')}"
        run_command(
            CommandRequest(
                command=[
                    "gh",
                    "repo",
                    "clone",
                    repository.repository,
                    str(path),
                    "--",
                    "--branch",
                    repository.branch,
                    "--single-branch",
                ],
                cwd=root,
                environment=environment,
            )
        )
        prepare_branch(path, repository.branch, branch, environment)
        starting_commit = run_command(
            CommandRequest(
                command=["git", "rev-parse", "HEAD"],
                cwd=path,
                environment=environment,
            )
        ).strip()

        repositories.append(
            RepositoryWorkspace(
                repository=repository.repository,
                branch=repository.branch,
                path=path,
                starting_commit=starting_commit,
            )
        )

    return AutomationWorkspace(root=root, branch=branch, repositories=repositories)


def prepare_branch(path: Path, base_branch: str, output: str, environment: dict[str, str]) -> None:
    """Check out an existing automation branch or create one from its base branch."""

    branch_exists = run_command(
        CommandRequest(
            command=["git", "ls-remote", "--heads", "origin", output],
            cwd=path,
            environment=environment,
        )
    ).strip()

    if branch_exists:
        run_command(
            CommandRequest(
                command=["git", "fetch", "origin", output],
                cwd=path,
                environment=environment,
            )
        )
        start_point = f"origin/{output}"
    else:
        start_point = f"origin/{base_branch}"

    run_command(
        CommandRequest(
            command=["git", "checkout", "-B", output, start_point],
            cwd=path,
            environment=environment,
        )
    )
    run_command(
        CommandRequest(
            command=["git", "config", "user.name", GIT_AUTHOR_NAME],
            cwd=path,
            environment=environment,
        )
    )
    run_command(
        CommandRequest(
            command=["git", "config", "user.email", GIT_AUTHOR_EMAIL],
            cwd=path,
            environment=environment,
        )
    )


def verify_origin(repository: RepositoryWorkspace, environment: dict[str, str]) -> None:
    """Require the repository origin to remain its configured GitHub remote."""

    origin = run_command(
        CommandRequest(
            command=["git", "remote", "get-url", "origin"],
            cwd=repository.path,
            environment=environment,
        )
    ).strip()
    match = GITHUB_ORIGIN_PATTERN.fullmatch(origin)

    if match is None or match.group(1) != repository.repository:
        raise DispatchError(f"repository origin changed for {repository.repository}")
