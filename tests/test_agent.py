import subprocess
from pathlib import Path

import pytest

from code_automations.agent import (
    clone_repositories,
    materialize_global_rule,
    materialize_skills,
    run_agent,
)
from code_automations.configuration import find_target, load_configuration
from code_automations.errors import DispatchError
from code_automations.models.configuration import ModelConfig
from code_automations.models.runtime import PreparedRepository


class TestAgent:
    """Test runner-local agent workspace preparation and execution."""

    def test_clone_repositories_uses_collision_safe_paths(
        self,
        automation_config_path: Path,
        prompts_directory: Path,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Clone configured branches without deriving paths from repository names."""

        target = find_target(
            load_configuration(automation_config_path, prompts_directory),
            "owner/repository",
            "hello-world",
        )
        commands: list[list[str]] = []

        def run(command: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
            """Capture a successful workspace command."""

            commands.append(command)

            return subprocess.CompletedProcess(command, 0, "", "")

        monkeypatch.setattr("code_automations.agent.run_command", run)

        repositories = clone_repositories(target, tmp_path / "workspace")

        assert [repository.path.name for repository in repositories] == ["0", "1"]
        assert ["--branch", "main", "--single-branch"] == commands[0][-3:]
        assert ["--branch", "develop", "--single-branch"] == commands[1][-3:]
        assert "owner/repository" in commands[0]
        assert "owner/secondary" in commands[1]

    def test_materialize_skills_copies_selected_native_skill(
        self,
        automation_config_path: Path,
        prompts_directory: Path,
        tmp_path: Path,
    ) -> None:
        """Copy configured Agent Sync skills into the temporary agent home."""

        loaded = load_configuration(automation_config_path, prompts_directory)
        target = find_target(loaded, "owner/repository", "hello-world")
        agent_home = tmp_path / "agent-home"
        agent_home.mkdir()

        materialize_skills(loaded, target, agent_home)

        skill = agent_home / "skills/example-skill/SKILL.md"

        assert skill.is_file()
        assert "Be concise." in skill.read_text(encoding="utf-8")

    def test_materialize_global_rule_uses_packaged_markdown(self, tmp_path: Path) -> None:
        """Create native coordination rules without embedding prompt prose in code."""

        materialize_global_rule(tmp_path)

        rule = (tmp_path / "AGENTS.md").read_text(encoding="utf-8")

        assert "read and follow its root instruction file" in rule
        assert "Do not merge any pull request" in rule
        assert "Codex" not in rule

    def test_run_agent_uses_local_ephemeral_multi_repository_session(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Run the selected model locally with every repository directory available."""

        repositories = [
            PreparedRepository(repository="owner/one", branch="main", path=tmp_path / "repositories/0"),
            PreparedRepository(repository="owner/two", branch="develop", path=tmp_path / "repositories/1"),
        ]
        commands: list[list[str]] = []

        def run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
            """Capture the agent invocation and write its final response."""

            commands.append(command)
            output_path = Path(command[command.index("--output-last-message") + 1])
            output_path.write_text("Created two pull requests.\n", encoding="utf-8")

            return subprocess.CompletedProcess(command, 0, "event output", "")

        monkeypatch.setattr("code_automations.agent.subprocess.run", run)

        response = run_agent(
            "Run the task.\n",
            ModelConfig(name="gpt-5.6-terra", reasoning_effort="high"),
            tmp_path,
            repositories,
        )

        command = commands[0]

        assert response == "Created two pull requests."
        assert command[:3] == ["codex", "exec", "--ephemeral"]
        assert "--dangerously-bypass-approvals-and-sandbox" in command
        assert "--skip-git-repo-check" in command
        assert command.count("--add-dir") == 2
        assert "gpt-5.6-terra" in command
        assert 'model_reasoning_effort="high"' in command
        assert command[-1] == "-"

    def test_run_agent_fails_closed(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Fail dispatch when the local agent process exits unsuccessfully."""

        monkeypatch.setattr(
            "code_automations.agent.subprocess.run",
            lambda *args, **kwargs: subprocess.CompletedProcess([], 1, "", "authentication failed"),
        )

        with pytest.raises(DispatchError, match="authentication failed"):
            run_agent("Run.", ModelConfig(), tmp_path, [])
