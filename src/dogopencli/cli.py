"""Public command routing for installed leaves, authentication and local controls."""

import sys

from .command_model import leading_command
from .errors import CliError

AUTH_COMMANDS = {"login", "auth", "logout"}


def main(argv: list[str] | None = None) -> int:
    values = list(sys.argv[1:] if argv is None else argv)
    from .command_model import emit_help, resolve

    try:
        invocation = resolve(values)
    except CliError as error:
        # Report auth argument failures through the existing auth envelope;
        # never fall back to an older help parser after failed validation.
        word, _ = leading_command(values)
        if word in AUTH_COMMANDS:
            from .auth.cli import error_dict
            from .auth.output import Result, emit
            from .browser.errors import invalid

            command = ".".join(error.command_path) if error.command_path else word
            output_format = "json"
            for position, token in enumerate(values):
                if token == "--format=text" or (
                    token == "--format"
                    and values[position + 1 : position + 2] == ["text"]
                ):
                    output_format = "text"
            emit(
                command,
                Result(exit_code=1),
                error_dict(invalid(error.message), command),
                output_format,
            )
            return 1
        from .leaves.cli import main as leaf_main

        return leaf_main(values)
    if invocation.args.version and invocation.node.path[:1] not in (
        ("login",),
        ("logout",),
        ("auth",),
    ):
        from .leaves.cli import main as leaf_main

        return leaf_main(["--version", "--format", invocation.args.format])
    if not invocation.args.version and (
        invocation.help_requested or invocation.node.handler is None
    ):
        return emit_help(invocation)
    path = invocation.node.path
    if path[:1] in (("domain",), ("gui",)):
        from .domain_cli import main as domain_main
        from .gui import main as gui_main

        management_main = domain_main if path[0] == "domain" else gui_main
        return management_main([*path[1:], *invocation.remaining])
    if path and path[0] in AUTH_COMMANDS:
        from .auth.cli import main as auth_main

        return auth_main([*path, *invocation.remaining], command_hint=path[0])
    from .leaves.cli import main as leaf_main

    return leaf_main([*path, *invocation.remaining])
