"""Record structured public leaf outcomes without inspecting terminal output."""

import sys
from collections.abc import Callable
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any

from .errors import CliError


@dataclass
class Observation:
    warning: bool = False
    error_code: str | None = None


_CURRENT: ContextVar[Observation | None] = ContextVar("leaf_observation", default=None)


def observe_result(meta: Any, error: Any = None) -> None:
    """Accept already-decided result metadata, never derive business policy."""
    current = _CURRENT.get()
    if current is None:
        return
    if isinstance(meta, dict) and meta.get("warnings"):
        current.warning = True
    if isinstance(error, dict) and isinstance(error.get("code"), str):
        current.error_code = error["code"]


def invoke_leaf(path: tuple[str, ...], handler: Callable[[], int]) -> int:
    """Gate once, execute once, and persist only completed leaf observations."""
    from .domains import DomainService, execution_owner

    if execution_owner(path) is None:
        return handler()
    service = DomainService()
    owner = service.require_execution(path)
    observation = Observation()
    token = _CURRENT.set(observation)
    code = 1
    try:
        code = handler()
        return code
    except CliError as exc:
        observation.error_code = exc.code
        code = exc.exit_code
        raise
    except KeyboardInterrupt:
        observation.error_code = "INTERRUPTED"
        code = 130
        raise
    except Exception:
        observation.error_code = "INTERNAL_ERROR"
        raise
    finally:
        _CURRENT.reset(token)
        operation = "list"
        from .plugins import domain_plugins

        for domain in domain_plugins():
            if domain.id == owner[0]:
                leaf = next(leaf for leaf in domain.leaves if leaf.id == owner[1])
                operation = dict(leaf.operations).get(path, "list")
                break
        outcome = "failed" if code else "warning" if observation.warning else "success"
        try:
            service.record_execution(
                *owner,
                outcome=outcome,
                operation=operation,
                error_code=observation.error_code if code else None,
            )
        except CliError:
            print(
                "warning: DOMAIN_STATE_ERROR: execution observation was not saved",
                file=sys.stderr,
            )
