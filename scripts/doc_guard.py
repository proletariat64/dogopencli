"""Check repository documentation conventions offline, without modifying files."""

from __future__ import annotations

import argparse
import os
import re
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT_DOCS = {"README.md", "AGENTS.md", "CONTEXT.md", "LICENSE.md"}
SKIP_DIRS = {
    "node_modules",
    "__pycache__",
    "build",
    "dist",
    "tmp",
    "aidb",
    "duckdog-data",
}
SLUG = r"[a-z0-9]+(?:-[a-z0-9]+)*"


def markdown_files(root: Path) -> list[Path]:
    """Inspect visible Markdown, including untracked files, but skip dependencies."""
    files = []
    for directory, dirs, names in os.walk(root, followlinks=False):
        dirs[:] = sorted(
            name
            for name in dirs
            if not name.startswith(".")
            and name not in SKIP_DIRS
            and not (Path(directory) / name).is_symlink()
        )
        files.extend(
            Path(directory) / name
            for name in sorted(names)
            if not name.startswith(".") and name.lower().endswith(".md")
        )
    return sorted(files)


def prose_lines(text: str) -> list[str]:
    """Ignore fenced examples when checking document titles and inline links."""
    lines = []
    fence = ""
    for line in text.splitlines():
        marker = re.match(r"^\s{0,3}(`{3,}|~{3,})", line)
        if marker:
            token = marker.group(1)
            if not fence:
                fence = token
            elif token[0] == fence[0] and len(token) >= len(fence):
                fence = ""
            lines.append("")
        else:
            lines.append("" if fence else line)
    return lines


def valid_layout(relative: Path) -> bool:
    parts = relative.parts
    if len(parts) == 1:
        return relative.name in ROOT_DOCS
    if len(parts) == 4 and parts[0] == "leaf_packages" and parts[3] == "README.md":
        return bool(
            re.fullmatch(SLUG, parts[1])
            and re.fullmatch(r"[a-z0-9]+(?:[._-][a-z0-9]+)*", parts[2])
        )
    if parts == ("docs", "README.md"):
        return True
    if len(parts) == 3 and parts[:2] == ("docs", "agents"):
        return bool(re.fullmatch(SLUG + r"\.md", parts[2]))
    return False


def check(root: Path) -> tuple[int, list[str]]:
    root = root.resolve()
    errors: list[str] = []
    files = markdown_files(root)
    for path in files:
        relative = path.relative_to(root)

        def error(message: str, relative: Path = relative) -> None:
            errors.append(f"{relative.as_posix()}: {message}")

        if not valid_layout(relative):
            error("invalid documentation directory or filename")
        if path.is_symlink():
            error("Markdown must be a regular file, not a symlink")
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            error(f"cannot read UTF-8 document: {exc}")
            continue
        prose = prose_lines(text)
        nonempty = [line for line in prose if line.strip()]
        if not nonempty or not re.match(r"^# \S", nonempty[0]):
            error("first content line must be an H1 title")
        if sum(bool(re.match(r"^# \S", line)) for line in prose) != 1:
            error("document must contain exactly one H1 title")
        if not text.endswith("\n"):
            error("missing final newline")
        for line_number, line in enumerate(prose, 1):
            line = re.sub(r"`[^`\n]*`", "", line)
            for match in re.finditer(r"!?\[[^\]\n]*\]\(([^)\n]+)\)", line):
                raw = match.group(1).strip()
                if not raw:
                    continue
                target = (
                    raw[1:].split(">", 1)[0] if raw.startswith("<") else raw.split()[0]
                )
                try:
                    parsed = urlsplit(target)
                except ValueError:
                    error(f"line {line_number}: malformed link: {target}")
                    continue
                if parsed.scheme or parsed.netloc or not parsed.path:
                    continue
                linked = (path.parent / unquote(parsed.path)).resolve()
                if not linked.is_relative_to(root):
                    error(
                        f"line {line_number}: local link escapes repository: {target}"
                    )
                elif not linked.exists():
                    error(f"line {line_number}: broken local link: {target}")
    if not files:
        errors.append("no Markdown documents found")
    return len(files), errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root", type=Path, default=Path(__file__).resolve().parents[1]
    )
    args = parser.parse_args()
    count, errors = check(args.root)
    if errors:
        for message in errors:
            print(f"ERROR {message}")
        print(f"doc-guard: FAIL ({len(errors)} errors, {count} Markdown files)")
        return 1
    print(f"doc-guard: PASS ({count} Markdown files)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
