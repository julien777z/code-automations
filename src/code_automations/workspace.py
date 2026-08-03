import hashlib
import logging
import subprocess
from importlib.resources import files
from pathlib import Path
from typing import Final

from code_automations.configuration import resolve_targets
from code_automations.errors import ConfigurationError, DispatchError
from code_automations.models.configuration import LoadedConfiguration, ResolvedRepository
from code_automations.models.runtime import WorkspaceAuthentication

logger = logging.getLogger(__name__)

__all__: Final[tuple[str, ...]] = ("prepare_workspace", "repository_path")

GLOBAL_RULE_PATH: Final[str] = "prompts/global.md"


def run_command(
    command: list[str],
    cwd: Path | None = None,
    input_text: str | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run one required workspace preparation command."""

    try:
        result = subprocess.run(
            command,
            cwd=cwd,
            input=input_text,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as error:
        raise DispatchError(f"unable to run {command[0]}: {error}") from error

    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or f"{command[0]} failed"

        raise DispatchError(detail)

    return result


def repository_path(workspace_root: Path, repository: str) -> Path:
    """Resolve one repository to a deterministic collision-safe workspace path."""

    identifier = hashlib.sha256(repository.casefold().encode()).hexdigest()

    return workspace_root / "repositories" / identifier


def configured_repositories(
    loaded: LoadedConfiguration,
    self_repository: str | None,
) -> list[ResolvedRepository]:
    """Collect unique repositories and require one base branch per repository."""

    repositories: dict[str, ResolvedRepository] = {}

    for target in resolve_targets(loaded, self_repository):
        for repository in target.repositories:
            key = repository.repository.casefold()
            existing = repositories.get(key)

            if existing is not None and existing.branch != repository.branch:
                raise ConfigurationError(f"repository has conflicting base branches: {repository.repository}")

            repositories[key] = repository

    return list(repositories.values())


def prepare_repository(repository: ResolvedRepository, path: Path) -> None:
    """Clone or reset one managed repository checkout."""

    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        run_command(
            [
                "git",
                "clone",
                "--branch",
                repository.branch,
                "--single-branch",
                f"https://github.com/{repository.repository}.git",
                str(path),
            ]
        )

        return

    if not (path / ".git").is_dir():
        raise DispatchError(f"managed repository path is not a Git checkout: {path}")

    run_command(["git", "reset", "--hard"], cwd=path)
    run_command(["git", "clean", "-fd"], cwd=path)
    run_command(["git", "fetch", "--prune", "origin", repository.branch], cwd=path)
    run_command(
        ["git", "checkout", "--force", "-B", repository.branch, f"origin/{repository.branch}"],
        cwd=path,
    )


def prepare_workspace(
    loaded: LoadedConfiguration,
    workspace_root: Path,
    self_repository: str | None,
) -> None:
    """Prepare authenticated repositories and native agent files in one agent workspace."""

    authentication = WorkspaceAuthentication()
    token = authentication.automation_github_token.get_secret_value()

    run_command(
        ["gh", "auth", "login", "--hostname", "github.com", "--with-token"],
        input_text=token,
    )
    run_command(["gh", "auth", "setup-git"])
    run_command(["git", "config", "--global", "user.name", "github-actions[bot]"])
    run_command(
        [
            "git",
            "config",
            "--global",
            "user.email",
            "41898282+github-actions[bot]@users.noreply.github.com",
        ]
    )

    for repository in configured_repositories(loaded, self_repository):
        if self_repository is not None and repository.repository.casefold() == self_repository.casefold():
            continue

        prepare_repository(repository, repository_path(workspace_root, repository.repository))

    instruction_path = workspace_root / "AGENTS.md"

    if instruction_path.exists():
        instruction_path.chmod(0o644)

    instruction_path.write_text(
        files("code_automations").joinpath(GLOBAL_RULE_PATH).read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    instruction_path.chmod(0o444)

    run_command(
        ["python", "-m", "agent_sync", "mirror-providers", "--root", str(loaded.root)],
        cwd=loaded.root,
    )

    logger.info("Prepared %s", loaded.root)
