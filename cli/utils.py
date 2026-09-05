import inspect
import functools

from typing import Callable
from typing import TypedDict

EMPTY = inspect.Parameter.empty


# PyCharm just wouldn't shut up without this.
class CommandData(TypedDict):
    func: Callable | None
    help: str
    params: dict


class ServiceCommandRegistry:
    def __init__(self, name: str, help_str: str):
        self.name = name
        self.help = help_str
        self.commands = {}

    def add_to_subparsers(self, subparsers):
        service_parser = subparsers.add_parser(
            name=self.name,
            help=self.help,
        )

        service_subparsers = service_parser.add_subparsers(
            dest="command",
            required=True,
        )

        for command_name, command_data in self.commands.items():
            command_parser = service_subparsers.add_parser(
                name=command_name,
                help=command_data["help"],
            )
            command_parser.set_defaults(func=command_data["func"])
            for param_name, param_data in command_data["params"].items():
                command_parser.add_argument(
                    f"--{param_name.replace('_', '-')}",
                    help=param_data["help"],
                    default=param_data["default"],
                    type=param_data["type"],
                )

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

    def command(self, **param_data):
        def decorator(func: Callable) -> Callable:
            command_name = func.__name__
            command_data: CommandData = {
                "func": None,  # Updated after wrapper function is created
                "help": (func.__doc__ or "").strip(),
                "params": {}
            }

            params = inspect.signature(func).parameters.values()
            for param in params:
                param_type = EMPTY
                if param.annotation is not EMPTY:
                    param_type = param.annotation
                elif param.default is not EMPTY:
                    param_type = type(param.default)

                default_help = f" (default: {param.default})" if param.default is not EMPTY else ""

                command_data["params"][param.name] = {
                    "type": param_type,
                    "default": param.default,
                    "help": str(param_data.get(param.name) or "") + default_help,
                }

            self.commands[command_name] = command_data

            @functools.wraps(func)
            def wrapper(**kwargs):
                kwargs = self.prompt_missing_required_args(command_data["params"], kwargs)
                return func(**kwargs)

            self.commands[command_name]["func"] = wrapper
            return wrapper

        return decorator
