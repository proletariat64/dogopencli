"""Small context-local execution facts, independent of storage and presentation."""

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any


@dataclass
class _Observer:
    callback: Callable[[dict[str, Any]], None]
    active: bool = True


_observer: ContextVar[_Observer | None] = ContextVar("progress_observer", default=None)
_facts: ContextVar[dict[str, Any] | None] = ContextVar("progress_facts", default=None)


@contextmanager
def observe(callback: Callable[[dict[str, Any]], None]) -> Iterator[None]:
    """Subscribe during this operation; exiting fences any copied context."""
    observer = _Observer(callback)
    token = _observer.set(observer)
    facts_token = _facts.set({})
    try:
        yield
    finally:
        observer.active = False
        _facts.reset(facts_token)
        _observer.reset(token)


def report(**values: Any) -> None:
    """Publish changed facts without replaying counters from a restored scope."""
    observer = _observer.get()
    if observer is None or not observer.active:
        return
    facts = _facts.get()
    if facts is None:
        facts = {}
    facts.update(values)
    try:
        observer.callback(dict(values))
    except Exception:
        # Telemetry failure must not change query acceptance or commit semantics.
        pass


@contextmanager
def scoped(**values: Any) -> Iterator[None]:
    """Isolate counters for one source/candidate without carrying business input."""
    token = _facts.set({**(_facts.get() or {}), **values})
    try:
        report(**values)
        yield
    finally:
        _facts.reset(token)


def advance(**increments: int) -> None:
    facts = _facts.get() or {}
    report(**{name: facts.get(name, 0) + value for name, value in increments.items()})
