import functools
import inspect
from typing import Dict
from typing import List
from typing import Callable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from argparse import ArgumentParser

EMPTY = inspect.Parameter.empty


def _class_name(cls) -> str:
    return cls.__name__.lower().replace("_", "-")


def _class_help(cls) -> str:
    return (cls.__doc__ or "").strip()


class Command:
    # Meant to be overridden by the child class to register its own subcommands.
    subcommands: List[type[SubCommand]]

    def modify_command_parser(self, command_parser):
        # Meant to be overridden by the child class to add arguments to the command itself, if need be.
        pass

    def add_to_subparsers(self, subparsers):
        command_parser = subparsers.add_parser(
            name=_class_name(self.__class__),
            help=_class_help(self),
        )

        self.modify_command_parser(command_parser)

        subcommand_parsers = command_parser.add_subparsers(
            dest="command",
            required=True,
        )

        for subcommand in self.subcommands:
            subcommand_parser = subcommand_parsers.add_parser(
                name=_class_name(subcommand),
                help=_class_help(subcommand),
            )

            signature = _generate_subcommand_signature(subcommand)

            for param_name, param_data in signature.items():
                if param_name in ("included_steps", "excluded_steps"):
                    continue
                subcommand_parser.add_argument(
                    f"--{param_name.replace('_', '-')}",
                    help=param_data["help"],
                    default=param_data["default"],
                    type=param_data["type"],
                )

            subcommand_parser.set_defaults(
                func=_subcommand_decorator(subcommand, signature),
            )

            _generate_step_options(subcommand, subcommand_parser)


def _generate_subcommand_param_help(subcommand: type[SubCommand]) -> dict:
    param_help = {}
    for cls in reversed(subcommand.__mro__):
        param_help.update(cls.__dict__.get("param_help", {}))

    return param_help


def _generate_subcommand_signature(subcommand: type[SubCommand]) -> dict:
    param_help = _generate_subcommand_param_help(subcommand)

    signature = {}
    for cls in reversed(subcommand.__mro__):
        if "__init__" not in cls.__dict__:
            continue

        signature.update(_parse_func_params(cls.__init__, param_help))

    return signature


def _parse_func_params(func: Callable, param_help: Dict[str, str]) -> Dict[str, Dict[str, str]]:
    params = list(inspect.signature(func).parameters.values())[1:]

    signature = {}
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

    return signature


def _subcommand_decorator(subcommand, signature):
    def wrapper(**kwargs):
        kwargs = _prompt_missing_required_args(signature, kwargs)
        subcommand(**kwargs).run()

    return wrapper


def _prompt_missing_required_args(params: dict, kwargs):
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


def _generate_step_options(subcommand: type[SubCommand], parser: ArgumentParser):
    steps = [
        getattr(method, "step_name")
        for method in vars(subcommand).values()
        if callable(method) and getattr(method, "is_step_function", False)
    ]

    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "-i", "--include-steps",
        help="Skip execution of any steps not included here.",
        action="extend",
        choices=steps,
        nargs="+",
        type=str,
        dest="included_steps",
    )
    group.add_argument(
        "-x", "--exclude-steps",
        help="Skip execution of any steps included here.",
        action="extend",
        choices=steps,
        nargs="+",
        type=str,
        dest="excluded_steps",
    )


class SubCommand:
    param_help: Dict[str, str]

    # noinspection bad-assignment
    def __init__(
            self,
            # This is intentional as the annotation here is passed to argparse as-is.
            included_steps: list = None,
            excluded_steps: list = None,
    ):
        self.included_steps: List[str] | None = included_steps
        self.excluded_steps: List[str] | None = excluded_steps

    def run(self):
        pass


def step(func):
    """Registers a SubCommand method as an individually executable step using the step subcommand."""
    name = func.__name__.replace("_", "-")

    @functools.wraps(func)
    def wrapper(self, *args, **kwargs):
        if self.included_steps and name not in self.included_steps:
            return None
        elif self.excluded_steps and name in self.excluded_steps:
            return None
        return func(self, *args, **kwargs)

    wrapper.is_step_function = True
    wrapper.step_name = name
    return wrapper
