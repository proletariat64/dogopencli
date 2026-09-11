"""Finite auth-command rendering; progress belongs on stderr.

Ported from DI ``src/di/cli/output.py`` at baseline commit
8eb163c6d140554ca167bd50349a85ca224ac342: the auth output protocol
(ADR 0004) is a ``output_version``/``command``/``exit_code``/``result``/
``error`` envelope, an explicit exception to the business data/meta/error
protocol.
"""

import json
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

OUTPUT_VERSION = 1


@dataclass
class Result:
    value: Any = None
    exit_code: int = 0
    text: str | None = None


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
        sys.stdout.write(json.dumps(envelope, ensure_ascii=False) + "\n")
    elif error:
        sys.stderr.write(f"{error['code']}: {error['message']}\n")
        for key, value in sorted(error.get("details", {}).items()):
            rendered = (
                value
                if isinstance(value, str)
                else json.dumps(value, ensure_ascii=False)
            )
            sys.stderr.write(f"{key}: {rendered}\n")
        if error.get("next"):
            sys.stderr.write("Next:\n")
            for step in error["next"]:
                sys.stderr.write(f"  {step}\n")
    elif result.text is not None:
        sys.stdout.write(result.text)
    elif isinstance(result.value, Mapping):
        for key, value in result.value.items():
            sys.stdout.write(f"{key}: {value}\n")
    elif result.value is not None:
        sys.stdout.write(json.dumps(result.value, ensure_ascii=False, indent=2) + "\n")
