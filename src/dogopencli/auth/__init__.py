"""Authentication commands: login, auth check, and the auth help group.

Ported from the DI unified CLI auth surface (``src/di/cli/`` arguments,
parser, help, output, errors and the ``di.cli.commands.auth`` adapter) at
baseline commit 8eb163c6d140554ca167bd50349a85ca224ac342, aligned to the
current valid parameters only: the deprecated ``browser_context`` positional
and the hidden ``--json`` alias are rejected; explicit JSON is
``--format json``. ``logout`` is issue #8 scope; the command tree reserves
the ``logout`` leaf for it.
"""
