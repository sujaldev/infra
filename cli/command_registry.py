import inspect
from pathlib import Path

from typing import List

EMPTY = inspect.Parameter.empty


def class_name(cls) -> str:
    return cls.__name__.lower().replace("_", "-")


def class_help(cls) -> str:
    return (cls.__doc__ or "").strip()


class Command:
    # Meant to be overridden by the child class to register its own subcommands.
    subcommands: List[type[SubCommand]]

    def modify_command_parser(self, command_parser):
        # Meant to be overridden by the child class to add arguments to the command itself, if need be.
        pass

    def add_to_subparsers(self, subparsers):
        command_parser = subparsers.add_parser(
            name=class_name(self.__class__),
            help=class_help(self),
        )

        self.modify_command_parser(command_parser)

        subcommand_parsers = command_parser.add_subparsers(
            dest="command",
            required=True,
        )

        for subcommand in self.subcommands:
            subcommand_parser = subcommand_parsers.add_parser(
                name=class_name(subcommand),
                help=class_help(subcommand),
            )

            param_help = {}
            for cls in reversed(subcommand.__mro__):
                param_help.update(cls.__dict__.get("param_help", {}))

            signature = {}
            for cls in reversed(subcommand.__mro__):
                if "__init__" not in cls.__dict__:
                    continue

                params = list(inspect.signature(cls.__init__).parameters.values())[1:]
                for param in params:
                    # Skip *args and **kwargs
                    if param.kind in (param.VAR_POSITIONAL, param.VAR_KEYWORD):
                        continue

                    param_type = EMPTY
                    if param.annotation is not EMPTY:
                        param_type = param.annotation
                    elif param.default is not EMPTY:
                        param_type = type(param.default)

                    default_help = f" (default: {param.default})" if param.default is not EMPTY else ""

                    signature[param.name] = {
                        "type": param_type,
                        "default": param.default,
                        "help": param_help.get(param.name, "") + default_help,
                    }

            for param_name, param_data in signature.items():
                subcommand_parser.add_argument(
                    f"--{param_name.replace('_', '-')}",
                    help=param_data["help"],
                    default=param_data["default"],
                    type=param_data["type"],
                )

            subcommand_parser.set_defaults(
                func=self.subcommand_decorator(subcommand, signature),
            )

    def subcommand_decorator(self, subcommand, signature):
        def wrapper(**kwargs):
            kwargs = self.prompt_missing_required_args(signature, kwargs)
            subcommand(**kwargs).run()

        return wrapper

    @staticmethod
    def prompt_missing_required_args(params: dict, kwargs):
        for param_name, param_data in params.items():
            is_required = param_data["default"] is EMPTY
            is_missing = kwargs.get(param_name, EMPTY) is EMPTY
            if not (is_required and is_missing):
                continue

            prompted_value = input(f"Enter value for required parameter {param_name!r}: ")
            if param_data["type"] not in (EMPTY, None):
                kwargs[param_name] = param_data["type"](prompted_value)
            else:
                kwargs[param_name] = prompted_value

        return kwargs


class SubCommand:
    def run(self):
        pass


def make_service_subcommand_base(default_service_user: str, default_service_home: Path):
    class ServiceSubCommandBase(SubCommand):
        param_help = {
            "service_user": f"Username of the host user that will run the rootless container.",
            "service_home": f"Path to the home directory of the service user.",
        }

        def __init__(
                self,
                service_user: str = default_service_user,
                service_home: Path = default_service_home,
        ):
            self.service_user = service_user
            self.service_home = service_home

    return ServiceSubCommandBase
