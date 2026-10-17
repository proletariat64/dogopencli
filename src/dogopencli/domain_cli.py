"""Public offline domain management commands."""

import argparse
import json
import sys

from . import config
from .auth.output import Result, emit
from .domains import DomainService
from .errors import CliError
from .helpspec import add_options
from .management import DOMAIN_ARGUMENT, DOMAIN_OPTIONS


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise CliError("INVALID_ARGUMENT", message, exit_code=2)


def main(argv: list[str]) -> int:
    parser = _Parser(prog="dogopencli domain", allow_abbrev=False, add_help=False)
    parser.add_argument(
        "action", nargs="?", choices=("list", "show", "leaves", "enable", "disable")
    )
    parser.add_argument(DOMAIN_ARGUMENT["name"], nargs="?")
    add_options(parser, DOMAIN_OPTIONS)
    parser.add_argument("--help", "-h", action="store_true")
    format = "json"
    command = "domain"
    try:
        args = parser.parse_intermixed_args(argv)
        format = args.format
        if args.help or args.action is None:
            from .command_model import emit_help, resolve

            return emit_help(resolve(["domain", *argv]))
        command = "domain " + args.action
        service = DomainService(config.config_path(args.config_dir))
        if args.action != "list" and args.domain is None:
            raise CliError("INVALID_ARGUMENT", "domain is required", exit_code=2)
        if args.action == "list" and args.domain is not None:
            raise CliError("INVALID_ARGUMENT", "list takes no domain", exit_code=2)
        rows = service.inventory(args.domain)
        value = rows if args.action == "list" else rows[0]
        if args.action == "leaves":
            value = rows[0]["leaves"]
        if args.action in {"enable", "disable"}:
            value = service.set_enabled(args.domain, args.action == "enable")
        emit(
            command,
            Result(value, text=json.dumps(value, indent=2) + "\n"),
            None,
            format,
        )
        return 0
    except CliError as exc:
        emit(
            command,
            Result(exit_code=exc.exit_code),
            {"code": exc.code, "message": exc.message, "retryable": exc.retryable},
            format,
        )
        return exc.exit_code
    except SystemExit as exc:
        return int(exc.code)
    except KeyboardInterrupt:
        sys.stderr.write("interrupted\n")
        return 130
