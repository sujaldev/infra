import argparse
import logging
from typing import TYPE_CHECKING

from pyinfra.api import Config
from pyinfra.api import Inventory
from pyinfra.api import State
from pyinfra.api.connect import connect_all
from pyinfra.api.exceptions import PyinfraError
from pyinfra.api.operation import add_op
from pyinfra.api.operations import run_ops
from rich.logging import RichHandler

if TYPE_CHECKING:
    from cli.utils import ServiceCommandRegistry

subcommands = [
]


def setup_logging():
    logging.basicConfig(
        level=logging.WARNING,
        handlers=[RichHandler()],
        format="[%(name)s]: %(message)s"
    )
    logging.getLogger("pyinfra").setLevel(logging.INFO)


def cli():
    parser = argparse.ArgumentParser(
        prog="infra",
        description="CLI to deploy and manage various services.",
    )

    parser.add_argument(
        "servers",
        help="Comma separated list of servers (defined in ~/.ssh/config) to operate on. "
             "Use @local for current host.",
        type=lambda servers: [server for server in servers.split(",") if server],
    )

    subparsers = parser.add_subparsers(required=True)

    for command in subcommands:
        command.add_to_subparsers(subparsers)

    args = parser.parse_args()

    return args


def main():
    args = cli()
    excluded_params = (
        "servers",
        "command",
        "func"
    )
    kwargs = {
        param: arg
        for param, arg in vars(args).items()
        if param not in excluded_params
    }

    setup_logging()

    inventory = Inventory((args.servers, {}))
    config = Config()
    state = State(inventory=inventory, config=config)

    try:
        connect_all(state)
    except PyinfraError as e:
        logging.error(e)
        return

    add_op(state, args.func, **kwargs)
    run_ops(state)
