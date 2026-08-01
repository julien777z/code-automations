import json
import logging
import shutil
import subprocess
from importlib.resources import files
from pathlib import Path
from typing import Final

from agent_sync.skill import load_skills
from agent_sync.workspace import Workspace

from code_automations.errors import DispatchError
from code_automations.models.configuration import AutomationTarget, LoadedConfiguration, ModelConfig
from code_automations.models.runtime import PreparedRepository
from code_automations.rendering import render_target

logger = logging.getLogger(__name__)

GLOBAL_RULE_PATH: Final[str] = "prompts/global.md"

__all__: Final[tuple[str, ...]] = ("run_target",)


def run_command(command: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    """Run one required workspace command."""

    try:
        result = subprocess.run(
            command,
            cwd=cwd,
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


def prepare_git() -> None:
    """Configure authenticated Git and GitHub CLI access for the runner."""

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


def clone_repositories(target: AutomationTarget, workspace_root: Path) -> list[PreparedRepository]:
    """Clone every configured repository into a collision-safe workspace path."""

    repositories_root = workspace_root / "repositories"
    repositories_root.mkdir(parents=True)
    prepared: list[PreparedRepository] = []

    for index, repository in enumerate(target.repositories):
        path = repositories_root / str(index)

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
        prepared.append(
            PreparedRepository(
                repository=repository.repository,
                branch=repository.branch,
                path=path,
            )
        )

    return prepared


def materialize_skills(loaded: LoadedConfiguration, target: AutomationTarget, agent_home: Path) -> None:
    """Copy selected canonical skills into the agent's native skill directory."""

    configured_skills = {skill.slug: skill for skill in load_skills(Workspace(root=loaded.root))}
    skills_root = agent_home / "skills"

    for slug in target.automation.skills:
        shutil.copytree(configured_skills[slug].directory, skills_root / slug, dirs_exist_ok=True)


def materialize_global_rule(workspace_root: Path) -> None:
    """Write the immutable global automation rule into the coordination workspace."""

    content = files("code_automations").joinpath(GLOBAL_RULE_PATH).read_text(encoding="utf-8")

    (workspace_root / "AGENTS.md").write_text(content, encoding="utf-8")


def run_agent(
    prompt: str,
    model: ModelConfig,
    workspace_root: Path,
    repositories: list[PreparedRepository],
) -> str:
    """Run one ephemeral local agent session across the prepared repositories."""

    output_path = workspace_root / "last-message.md"
    command = [
        "codex",
        "exec",
        "--ephemeral",
        "--dangerously-bypass-approvals-and-sandbox",
        "--skip-git-repo-check",
        "--cd",
        str(workspace_root),
        "--model",
        model.name,
        "--config",
        f"model_reasoning_effort={json.dumps(model.reasoning_effort)}",
        "--output-last-message",
        str(output_path),
    ]

    for repository in repositories:
        command.extend(["--add-dir", str(repository.path)])

    command.append("-")

    try:
        result = subprocess.run(
            command,
            input=prompt,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as error:
        raise DispatchError(f"unable to start the agent: {error}") from error

    if result.stdout.strip():
        logger.info(result.stdout.strip())

    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or "agent execution failed"

        raise DispatchError(detail)

    if not output_path.is_file():
        raise DispatchError("agent execution did not produce a final response")

    return output_path.read_text(encoding="utf-8").strip()


def report_run(summary_path: Path | None, target: AutomationTarget, final_response: str) -> None:
    """Append one completed automation response to the Actions summary."""

    if summary_path is None:
        return

    with summary_path.open("a", encoding="utf-8") as summary:
        summary.write(f"## {target.name}\n\n{final_response}\n")


def run_target(
    loaded: LoadedConfiguration,
    target: AutomationTarget,
    workspace_root: Path,
    agent_home: Path,
    summary_path: Path | None,
) -> None:
    """Prepare and run one local multi-repository automation session."""

    prepare_git()
    session_root = workspace_root / target.name
    session_root.mkdir(parents=True)

    repositories = clone_repositories(target, session_root)

    materialize_skills(loaded, target, agent_home)
    materialize_global_rule(session_root)

    final_response = run_agent(
        render_target(loaded, target, repositories),
        target.model,
        session_root,
        repositories,
    )

    report_run(summary_path, target, final_response)
