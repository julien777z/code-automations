import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Final

from code_automations.agent import run_target
from code_automations.configuration import (
    find_target,
    load_configuration,
    resolve_self_repository,
    resolve_targets,
)
from code_automations.errors import ConfigurationError, DispatchError
from code_automations.models.runtime import ActionsContext, CliArguments
from code_automations.rendering import render_target
from code_automations.scheduling import dispatcher_occurrence, due_automations
from code_automations.utils import parse_datetime

logger = logging.getLogger(__name__)

__all__: Final[tuple[str, ...]] = ("run",)


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line interface."""

    parser = argparse.ArgumentParser(prog="code-automations")
    parser.add_argument("--config", type=Path, default=Path("automations.yaml"))
    parser.add_argument("--prompts-directory", type=Path, required=True)

    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("validate")

    render_parser = subparsers.add_parser("render")
    render_parser.add_argument("automation")

    due_parser = subparsers.add_parser("due")
    due_parser.add_argument("--now")
    due_parser.add_argument("--dispatcher-schedule")

    dispatch_parser = subparsers.add_parser("dispatch")
    selection = dispatch_parser.add_mutually_exclusive_group(required=True)
    selection.add_argument("--automation")
    selection.add_argument("--scheduled", action="store_true")
    dispatch_parser.add_argument("--now")
    dispatch_parser.add_argument("--dispatcher-schedule")
    dispatch_parser.add_argument("--workspace", type=Path, required=True)
    dispatch_parser.add_argument("--agent-home", type=Path, required=True)

    return parser


def run(arguments: CliArguments) -> int:
    """Run a parsed CLI command."""

    context = ActionsContext()

    if arguments.command == "validate":
        load_configuration(arguments.config, arguments.prompts_directory)

        logger.info("Configuration is valid.")

        return 0

    loaded = load_configuration(arguments.config, arguments.prompts_directory)
    self_repository = resolve_self_repository(loaded, context.github_repository)

    if arguments.command == "render":
        if arguments.automation is None:
            raise ConfigurationError("render requires an automation name")

        target = find_target(loaded, self_repository, arguments.automation)
        logger.info(render_target(loaded, target).removesuffix("\n"))

        return 0

    now = parse_datetime(arguments.now)
    occurrence = (
        dispatcher_occurrence(arguments.dispatcher_schedule, now) if arguments.dispatcher_schedule else now
    )
    targets = resolve_targets(loaded, self_repository)

    if arguments.command == "due":
        due = due_automations(targets, occurrence)
        logger.info(
            json.dumps(
                [
                    {
                        "automation": item.name,
                        "scheduled_for": item.scheduled_for.isoformat(),
                    }
                    for item in due
                ],
                indent=2,
            )
        )

        return 0

    if arguments.workspace is None or arguments.agent_home is None:
        raise ConfigurationError("dispatch requires workspace and agent home paths")

    selected_targets = (
        [find_target(loaded, self_repository, arguments.automation)]
        if arguments.automation is not None
        else [find_target(loaded, self_repository, due.name) for due in due_automations(targets, occurrence)]
    )

    for target in selected_targets:
        run_target(
            loaded,
            target,
            arguments.workspace,
            arguments.agent_home,
            context.github_step_summary,
        )

    return 0


if __name__ == "__main__":
    logging.basicConfig(format="%(message)s", level=logging.INFO, stream=sys.stdout)

    arguments = CliArguments.model_validate(vars(build_parser().parse_args()))

    try:
        exit_code = run(arguments)
    except (ConfigurationError, DispatchError, ValueError) as error:
        logger.error(error)
        exit_code = 1

    raise SystemExit(exit_code)
