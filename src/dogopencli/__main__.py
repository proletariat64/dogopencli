"""Thin entry point for python -m dogopencli."""

from .cli import main

if __name__ == "__main__":
    raise SystemExit(main())
