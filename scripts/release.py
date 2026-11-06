"""Publish a merged GitHub version locally to the selected artifact host."""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

ROOT = Path(__file__).resolve().parents[1]
PROJECT = "pd.pt/dogopencli"
REMOTE = "https://github.com/proletariat64/dogopencli.git"
TRUSTED_ORIGINS = {REMOTE, "git@github.com:proletariat64/dogopencli.git"}
GIT = ["git"]


def run(arguments: list[str], root: Path) -> str:
    result = subprocess.run(
        arguments,
        cwd=root,
        text=True,
        capture_output=True,
        timeout=600,
        check=False,
        env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
    )
    if result.returncode:
        # Provider output may contain credentials.
        raise RuntimeError(
            f"command failed: {' '.join(arguments[:3])} (exit {result.returncode})"
        )
    return result.stdout.strip()


def package_version(root: Path) -> str:
    with (root / "pyproject.toml").open("rb") as stream:
        return tomllib.load(stream)["project"]["version"]


def version_tuple(value: str) -> tuple[int, ...]:
    if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", value):
        raise ValueError("version must be MAJOR.MINOR.PATCH")
    parts = tuple(int(part) for part in value.split("."))
    if value != ".".join(str(part) for part in parts):
        raise ValueError("version must not contain leading zeroes")
    return parts


def remote_tag(root: Path, tag: str) -> str | None:
    records = run(
        [
            *GIT,
            "ls-remote",
            "--tags",
            REMOTE,
            f"refs/tags/{tag}",
            f"refs/tags/{tag}^{{}}",
        ],
        root,
    )
    refs = dict(line.split(maxsplit=1)[::-1] for line in records.splitlines() if line)
    return refs.get(f"refs/tags/{tag}^{{}}") or refs.get(f"refs/tags/{tag}")


def release(
    root: Path = ROOT,
    *,
    target: str | None = None,
    dry_run: bool = False,
    retry: bool = False,
    provider: str = "antcode",
) -> str:
    if provider not in {"antcode", "github"}:
        raise ValueError("target must be antcode or github")
    version = package_version(root)
    version_tuple(version)
    if target is not None and target != version:
        raise ValueError(
            "VERSION must equal the merged project version; bump it in a GitHub PR"
        )
    tag = f"v{version}"
    origin = run(["git", "remote", "get-url", "origin"], root)
    if origin not in TRUSTED_ORIGINS:
        raise ValueError(
            "origin must identify the trusted GitHub dogopencli repository"
        )
    branch = run(["git", "symbolic-ref", "--quiet", "--short", "HEAD"], root)
    if branch != "master":
        raise ValueError(
            "release requires attached master after the GitHub PR is merged"
        )
    dirty = bool(run(["git", "status", "--porcelain"], root))
    print(f"Release {tag}: GitHub source, {provider} artifacts")
    if dry_run:
        print("Dry run: no checks, edits, commits, tags or network writes.")
        print(
            "Commit working-tree changes first." if dirty else "Working tree is clean."
        )
        print(
            f"Current merged version: {version}. "
            "Plan: fetch origin/master; verify HEAD; "
            "make check; make smoke; create/push GitHub tag only; publish locally."
        )
        return tag
    if dirty:
        raise ValueError(
            "working tree is not clean; commit your development changes first"
        )
    # Fetch the explicit trusted URL, not a configurable origin fetch refspec.
    run(
        [
            "git",
            "fetch",
            "--no-tags",
            REMOTE,
            "+refs/heads/master:refs/remotes/origin/master",
        ],
        root,
    )
    commit = run(["git", "rev-parse", "HEAD"], root)
    if run(["git", "rev-parse", "refs/remotes/origin/master"], root) != commit:
        raise ValueError(
            "HEAD must match freshly fetched origin/master; merge and pull first"
        )
    local = run(["git", "tag", "--list", tag], root)
    existing = remote_tag(root, tag)
    if local and run(["git", "rev-parse", f"{tag}^{{commit}}"], root) != commit:
        raise ValueError("local tag points elsewhere; refusing to replace it")
    if existing and existing != commit:
        raise ValueError("remote tag points elsewhere; refusing to replace it")
    if not retry and (local or existing):
        raise ValueError(f"{tag} already exists; use make release RETRY=1")
    run(["make", "check"], root)
    run(["make", "smoke"], root)
    if run(["git", "status", "--porcelain"], root):
        raise ValueError("working tree changed during checks; refusing publication")
    if not local:
        run(["git", "tag", "-a", tag, "-m", f"Release {tag}"], root)
    if not existing:
        try:
            run([*GIT, "push", REMOTE, f"refs/tags/{tag}"], root)
        except (RuntimeError, OSError, subprocess.TimeoutExpired) as error:
            raise RuntimeError(
                f"{tag} remains local; fix push access, then run "
                f"make release RETRY=1 TARGET={provider}"
            ) from error
    try:
        run(["make", "publish-release", f"TAG={tag}", f"TARGET={provider}"], root)
    except (RuntimeError, OSError, subprocess.TimeoutExpired) as error:
        raise RuntimeError(
            f"{tag} is pushed but publication failed; run "
            f"make release RETRY=1 TARGET={provider}"
        ) from error
    print(f"Published {tag} to {provider}.")
    return tag


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--version",
        default=os.environ.get("VERSION") or None,
        help="assert the already merged project version; never bumps versions",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=os.environ.get("DRY_RUN") == "1",
    )
    parser.add_argument(
        "--retry",
        action="store_true",
        default=os.environ.get("RETRY") == "1",
        help="retry the current version's local build, tag push and publication",
    )
    parser.add_argument("--target", choices=["antcode", "github"], default="antcode")
    args = parser.parse_args()
    try:
        release(
            target=args.version,
            dry_run=args.dry_run,
            retry=args.retry,
            provider=args.target,
        )
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as error:
        print(f"release: FAIL: {error}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
