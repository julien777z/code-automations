import json
import os
import subprocess
import sys
from pathlib import Path

import yaml


class TestAction:
    """Test the reusable GitHub Action contract."""

    def test_composite_action_launches_cloud_task(self) -> None:
        """Expose Cloud dispatch and durable authentication inputs."""

        action_path = Path(__file__).parents[1] / "action.yml"
        action_script_path = Path(__file__).parents[1] / ".github/scripts/action.py"
        bootstrap_script_path = Path(__file__).parents[1] / ".github/scripts/bootstrap.py"
        config_script_path = Path(__file__).parents[1] / ".github/scripts/config.py"
        action = yaml.safe_load(action_path.read_text(encoding="utf-8"))
        inputs = action["inputs"]
        rendered = action_path.read_text(encoding="utf-8")
        action_script = action_script_path.read_text(encoding="utf-8")
        bootstrap_script = bootstrap_script_path.read_text(encoding="utf-8")
        config_script = config_script_path.read_text(encoding="utf-8")

        assert action["runs"]["using"] == "composite"
        assert set(inputs) == {
            "automations-file-path",
            "codex-auth-json",
            "codex-environment-id",
            "github-token",
            "mode",
            "prompts-directory-path",
            "run-automation-name",
        }
        assert inputs["github-token"]["required"] is False
        assert inputs["github-token"]["default"] == ""
        assert "docker build" not in rendered
        assert 'case "$AUTOMATION_MODE"' not in rendered
        assert "automation_command=(" not in rendered
        assert 'python "$GITHUB_ACTION_PATH/.github/scripts/action.py"' in rendered
        assert '"npm", "ci", "--omit=dev", "--prefix"' in bootstrap_script
        assert "environment_value" not in action_script
        assert "BaseSettings" in config_script
        assert "Persist Automation Authentication" in rendered
        assert "inputs.github-token || github.token" in rendered
        assert '"--environment",' in action_script
        assert '"--branch",' in action_script
        assert "cwd=config.github_workspace" in action_script
        assert "CODEX_ENVIRONMENT_ID" in rendered
        assert "codex_environment_id" in config_script
        assert 'gh", "secret", "set", "CODEX_AUTH_JSON' in action_script
        assert "scheduled dispatch is only allowed from the default branch" in config_script
        assert 'github_event_name != "workflow_dispatch"' in config_script

    def test_release_workflow_publishes_v0_alpha_tags(self) -> None:
        """Publish immutable patch tags and update the moving v0 tag."""

        workflow_path = Path(__file__).parents[1] / ".github/workflows/publish-release.yml"
        workflow = workflow_path.read_text(encoding="utf-8")

        assert '"v0.0.*"' in workflow
        assert "git tag -f v0" in workflow
        assert "git push origin -f v0" in workflow
        assert "workflow_dispatch" not in workflow

    def test_documentation_disables_checkout_credentials(self) -> None:
        """Keep consumer checkout credentials disabled."""

        readme_path = Path(__file__).parents[1] / "README.md"

        assert "persist-credentials: false" in readme_path.read_text(encoding="utf-8")

    def test_authentication_setup_uses_permission_restricted_files(self, tmp_path: Path) -> None:
        """Store Cloud authentication in a locked-down temporary home."""

        script_path = Path(__file__).parents[1] / ".github/scripts/action.py"
        output_path = tmp_path / "output"
        environment = os.environ.copy()
        environment.update(
            CODEX_AUTH_JSON=json.dumps({"tokens": {"access_token": "test"}}),
            GITHUB_OUTPUT=str(output_path),
            RUNNER_TEMP=str(tmp_path),
        )

        subprocess.run(
            [sys.executable, str(script_path), "setup-authentication"],
            check=True,
            env=environment,
        )

        authentication_home = tmp_path / "automation-authentication"
        assert (authentication_home / "auth.json").stat().st_mode & 0o777 == 0o600
        assert (authentication_home / "config.toml").read_text(encoding="utf-8") == (
            'cli_auth_credentials_store = "file"\n'
        )
        assert output_path.read_text(encoding="utf-8") == f"home={authentication_home}\n"

    def test_refreshed_authentication_is_written_to_consumer_secret(self, tmp_path: Path) -> None:
        """Persist the refreshed authentication document without logging its contents."""

        script_path = Path(__file__).parents[1] / ".github/scripts/action.py"
        authentication_home = tmp_path / "authentication"
        binary_directory = tmp_path / "bin"
        arguments_path = tmp_path / "arguments"
        input_path = tmp_path / "input"
        authentication_home.mkdir()
        binary_directory.mkdir()
        authentication = json.dumps({"tokens": {"refresh_token": "refreshed"}})
        (authentication_home / "auth.json").write_text(authentication, encoding="utf-8")
        fake_gh = binary_directory / "gh"
        fake_gh.write_text(
            f"#!{sys.executable}\n"
            "import os\n"
            "import pathlib\n"
            "import sys\n"
            "pathlib.Path(os.environ['ARGUMENTS_PATH']).write_text(' '.join(sys.argv[1:]))\n"
            "pathlib.Path(os.environ['INPUT_PATH']).write_text(sys.stdin.read())\n",
            encoding="utf-8",
        )
        fake_gh.chmod(0o755)
        environment = os.environ.copy()
        environment.update(
            ARGUMENTS_PATH=str(arguments_path),
            CODEX_HOME=str(authentication_home),
            GH_TOKEN="token",
            GITHUB_REPOSITORY="owner/consumer",
            INPUT_PATH=str(input_path),
            PATH=f"{binary_directory}{os.pathsep}{environment['PATH']}",
        )

        subprocess.run(
            [sys.executable, str(script_path), "persist-authentication"],
            check=True,
            env=environment,
            capture_output=True,
            text=True,
        )

        assert arguments_path.read_text(encoding="utf-8") == (
            "secret set CODEX_AUTH_JSON --repo owner/consumer"
        )
        assert input_path.read_text(encoding="utf-8") == authentication
