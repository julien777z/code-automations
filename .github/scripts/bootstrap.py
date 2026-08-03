import argparse
import subprocess
import sys
from pathlib import Path
from typing import Final

BOOTSTRAP_COMMANDS: Final[tuple[str, ...]] = ("install-dependencies", "read-node-version")


def read_node_version(action_path: Path, github_output: Path) -> None:
    """Expose the action-owned Node.js version."""

    version = (action_path / ".nvmrc").read_text(encoding="utf-8").strip()

    with github_output.open("a", encoding="utf-8") as output:
        output.write(f"version={version}\n")


def install_dependencies(action_path: Path) -> None:
    """Install the action runtime dependencies."""

    subprocess.run(
        [sys.executable, "-m", "pip", "install", "--disable-pip-version-check", "poetry==2.2.0"],
        check=True,
    )
    subprocess.run(["poetry", "--directory", action_path, "install", "--only", "main"], check=True)
    subprocess.run(["npm", "ci", "--omit=dev", "--prefix", action_path], check=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=BOOTSTRAP_COMMANDS)
    parser.add_argument("--action-path", type=Path, required=True)
    parser.add_argument("--github-output", type=Path)
    arguments = parser.parse_args()

    match arguments.command:
        case "install-dependencies":
            install_dependencies(arguments.action_path)
        case "read-node-version":
            if arguments.github_output is None:
                parser.error("read-node-version requires --github-output")

            read_node_version(arguments.action_path, arguments.github_output)
