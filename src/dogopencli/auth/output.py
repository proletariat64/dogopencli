"""Finite auth-command rendering; progress belongs on stderr.

Ported from DI ``src/di/cli/output.py`` at baseline commit
8eb163c6d140554ca167bd50349a85ca224ac342: the auth output protocol
(ADR 0004) is a ``output_version``/``command``/``exit_code``/``result``/
``error`` envelope, an explicit exception to the business data/meta/error
protocol.
"""

import sys
from dataclasses import dataclass
from typing import Any

from ..jsonutil import canonical
from ..rendering import render_text

OUTPUT_VERSION = 1


@dataclass
class Result:
    value: Any = None
    exit_code: int = 0


def emit(
    command: str, result: Result, error: dict[str, Any] | None, format: str
) -> None:
    envelope = {
        "output_version": OUTPUT_VERSION,
        "command": command,
        "exit_code": result.exit_code,
        "result": None if error else result.value,
        "error": error,
    }
    if format == "json":
        sys.stdout.write(canonical(envelope) + "\n")
    elif error:
        sys.stderr.write(f"{error['code']}: {error['message']}\n")
        if error.get("details"):
            sys.stderr.write(render_text(dict(sorted(error["details"].items()))) + "\n")
        if error.get("next"):
            sys.stderr.write("Next:\n")
            sys.stderr.write(render_text(error["next"], 1) + "\n")
    elif result.value is not None:
        sys.stdout.write(render_text(result.value) + "\n")
