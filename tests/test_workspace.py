import hashlib
import subprocess
from pathlib import Path

import pytest

from code_automations.configuration import load_configuration
from code_automations.models.configuration import ResolvedRepository
from code_automations.workspace import prepare_repository, prepare_workspace, repository_path


class TestWorkspace:
    """Test reusable Cloud workspace preparation."""

    def test_repository_path_is_deterministic_and_collision_safe(self, tmp_path: Path) -> None:
        """Map full repository identities to stable paths."""

        expected = hashlib.sha256(b"owner/repository").hexdigest()

        assert repository_path(tmp_path, "Owner/Repository") == tmp_path / "repositories" / expected
        assert repository_path(tmp_path, "owner/other") != repository_path(tmp_path, "other/repository")

    def test_prepare_workspace_authenticates_clones_and_syncs_native_files(
        self,
        automation_config_path: Path,
        prompts_directory: Path,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Prepare managed checkouts and native instructions with setup authentication."""

        commands: list[tuple[list[str], Path | None, str | None]] = []

        def run_command(
            command: list[str], cwd: Path | None = None, input_text: str | None = None
        ) -> subprocess.CompletedProcess[str]:
            """Capture one workspace preparation command."""

            commands.append((command, cwd, input_text))

            return subprocess.CompletedProcess(args=command, returncode=0, stdout="", stderr="")

        monkeypatch.setenv("AUTOMATION_GITHUB_TOKEN", "token")
        monkeypatch.setattr("code_automations.workspace.run_command", run_command)
        loaded = load_configuration(automation_config_path, prompts_directory)

        prepare_workspace(loaded, tmp_path / "workspace", "owner/repository")

        assert commands[0][0][:3] == ["gh", "auth", "login"]
        assert commands[0][2] == "token"
        assert any(command[:2] == ["git", "clone"] for command, _, _ in commands)
        assert commands[-1][0][:4] == ["python", "-m", "agent_sync", "mirror-providers"]
        instruction = tmp_path / "workspace/AGENTS.md"
        assert "Do not merge any pull request" in instruction.read_text(encoding="utf-8")
        assert instruction.stat().st_mode & 0o777 == 0o444

    def test_prepare_repository_resets_cached_checkout(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Reset only an existing managed checkout to its configured branch."""

        checkout = tmp_path / "checkout"
        (checkout / ".git").mkdir(parents=True)
        commands: list[list[str]] = []
        monkeypatch.setattr(
            "code_automations.workspace.run_command",
            lambda command, cwd=None, input_text=None: commands.append(command),
        )

        prepare_repository(ResolvedRepository(repository="owner/repository", branch="main"), checkout)

        assert commands == [
            ["git", "reset", "--hard"],
            ["git", "clean", "-fd"],
            ["git", "fetch", "--prune", "origin", "main"],
            ["git", "checkout", "--force", "-B", "main", "origin/main"],
        ]
