#!/usr/bin/env python3
"""Publish built dogopencli packages without replacing existing release assets."""

import argparse
import hashlib
import importlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:
    tomllib = importlib.import_module("tomli")

ROOT = Path(__file__).resolve().parents[1]
SOURCE_URL = "https://github.com/proletariat64/dogopencli"
SOURCE_REMOTE = f"{SOURCE_URL}.git"


class PublishError(Exception):
    """A safe-to-display publication failure."""


def command(*args: str, absent_ok: bool = False) -> str | None:
    """Capture provider output; never expose credentials or raw provider errors."""
    if not args:
        raise PublishError("command requires an executable")
    program = args[0]
    try:
        result = subprocess.run(
            args, cwd=ROOT, capture_output=True, text=True, timeout=180, check=False
        )
    except (OSError, subprocess.TimeoutExpired):
        raise PublishError(f"{program} command unavailable or timed out") from None
    if result.returncode:
        # A numeric HTTP status, not an arbitrary occurrence inside a URL/body.
        statuses = re.findall(
            r"(?:HTTP(?:/\d(?:\.\d)?)?\s+|status(?: code)?\s*[:=]?\s*|:\s*|\()"
            r"([45]\d\d)\b",
            result.stderr + "\n" + result.stdout,
            re.IGNORECASE,
        )
        missing_release = (
            args[1:3] == ("release", "show")
            and len(args) > 3
            and re.fullmatch(
                r"antcode: error: failed to get release: release "
                rf"'{re.escape(str(args[3]))}' "
                r"not found in repository [0-9]+",
                result.stderr.strip(),
            )
            is not None
        )
        if absent_ok and (
            (statuses and set(statuses) == {"404"})
            or (not statuses and missing_release)
        ):
            return None
        raise PublishError(f"{program} command failed (exit {result.returncode})")
    return result.stdout


def decode(output):
    try:
        value = json.loads(output)
    except (ValueError, TypeError):
        raise PublishError("Invalid release provider JSON response") from None
    if not isinstance(value, dict):
        raise PublishError("Invalid release provider JSON object")
    return value


def publish(tag, dist, project, require_token=False, target="antcode"):
    if target not in {"antcode", "github"}:
        raise PublishError("Target must be antcode or github")
    if target == "github" and project != "proletariat64/dogopencli":
        raise PublishError("GitHub destination must be the trusted source repository")
    if target == "github" and require_token:
        raise PublishError(
            "--require-token is AntCode-only; authenticate with gh auth login"
        )
    if require_token and not os.environ.get("ANTCODE_SECRET_TOKEN", "").strip():
        raise PublishError("ANTCODE_SECRET_TOKEN is required")
    with (ROOT / "pyproject.toml").open("rb") as stream:
        version = tomllib.load(stream)["project"]["version"]
    if not isinstance(version, str) or not re.fullmatch(
        r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)", version
    ):
        raise PublishError("Version must be canonical numeric major.minor.patch")
    if not re.fullmatch(
        r"[A-Za-z0-9][A-Za-z0-9._-]*/[A-Za-z0-9][A-Za-z0-9._-]*", project
    ):
        raise PublishError("Project must be a safe namespace/project path")
    if tag != f"v{version}":
        raise PublishError("Tag must equal v<pyproject.toml version>")
    if (command("git", "status", "--porcelain") or "").strip():
        raise PublishError("Git working tree must be clean")
    head = (command("git", "rev-parse", "HEAD") or "").strip()
    if not re.fullmatch(r"[0-9a-f]{40}", head):
        raise PublishError("Invalid Git HEAD")

    def api(*args, absent_ok=False):
        return command("antcode", *args, "--project", project, absent_ok=absent_ok)

    def github_show(absent_ok=False):
        # The tag endpoint describes published releases. List all pages so an
        # authenticated draft can be resumed even when it is not on page one.
        response = command(
            "gh",
            "api",
            f"repos/{project}/releases?per_page=100",
            "--paginate",
            "--slurp",
        )
        try:
            pages = json.loads(response)
        except (ValueError, TypeError):
            raise PublishError("Invalid GitHub release list") from None
        if not isinstance(pages, list) or any(
            not isinstance(page, list) or any(not isinstance(row, dict) for row in page)
            for page in pages
        ):
            raise PublishError("Invalid GitHub release list")
        matches = [row for page in pages for row in page if row.get("tag_name") == tag]
        if not matches and absent_ok:
            return None
        if len(matches) != 1:
            raise PublishError("Missing or ambiguous GitHub release")
        value = matches[0]
        if (
            not {"id", "tag_name", "target_commitish", "draft", "body", "assets"}
            <= value.keys()
        ):
            raise PublishError("Incomplete GitHub release JSON")
        if not isinstance(value["assets"], list) or any(
            not isinstance(row, dict) or not {"name", "size"} <= row.keys()
            for row in value["assets"]
        ):
            raise PublishError("Invalid GitHub release assets")
        return json.dumps(
            {
                "id": value["id"],
                "tag_name": value["tag_name"],
                "revision": value["target_commitish"],
                "is_draft": value["draft"],
                "description": value["body"],
                "assets": [
                    {"filename": row["name"], "size": row["size"]}
                    for row in value["assets"]
                ],
            }
        )

    def show(absent_ok=False):
        if target == "github":
            return github_show(absent_ok)
        return api("release", "show", tag, "--json", absent_ok=absent_ok)

    origin = (command("git", "remote", "get-url", "origin") or "").strip()
    if origin not in {SOURCE_REMOTE, "git@github.com:proletariat64/dogopencli.git"}:
        raise PublishError(
            "origin must identify the trusted GitHub dogopencli repository"
        )
    if (command("git", "rev-parse", f"{tag}^{{commit}}") or "").strip() != head:
        raise PublishError("Local source tag commit does not match HEAD")
    records = (
        command(
            "git",
            "ls-remote",
            "--tags",
            SOURCE_REMOTE,
            f"refs/tags/{tag}",
            f"refs/tags/{tag}^{{}}",
        )
        or ""
    )
    refs = dict(line.split(maxsplit=1)[::-1] for line in records.splitlines() if line)
    remote_head = refs.get(f"refs/tags/{tag}^{{}}") or refs.get(f"refs/tags/{tag}")
    if remote_head != head:
        raise PublishError("GitHub source tag commit does not match HEAD")
    response = show(absent_ok=True)
    release = decode(response) if response is not None else None

    def validate(value):
        if not {"id", "tag_name", "revision", "is_draft"} <= value.keys():
            raise PublishError("Incomplete release JSON")
        if value["tag_name"] != tag or not isinstance(value["is_draft"], bool):
            raise PublishError("Invalid release identity")
        description = value.get("description")
        if (
            not isinstance(description, str)
            or re.findall(r"(?m)^Source-Commit: (.*)$", description) != [head]
            or f"Source-Tag: {SOURCE_URL}/tree/{tag}" not in description.splitlines()
            or f"Source-URL: {SOURCE_URL}/commit/{head}" not in description.splitlines()
        ):
            raise PublishError("Release source provenance does not match GitHub HEAD")
        if not isinstance(value["revision"], str) or not re.fullmatch(
            r"[0-9a-f]{40}", value["revision"]
        ):
            raise PublishError("Invalid release revision")
        if target == "github" and value["revision"] != head:
            raise PublishError("GitHub release revision does not match HEAD")
        value.setdefault("assets", [])
        if not isinstance(value["assets"], list):
            raise PublishError("Invalid release assets")
        return value

    def assets(value):
        rows = value["assets"]
        if any(
            not isinstance(row, dict)
            or not {"filename", "size"} <= row.keys()
            or not isinstance(row["filename"], str)
            for row in rows
        ):
            raise PublishError("Invalid release asset JSON")
        names = [row["filename"] for row in rows]
        if len(set(names)) != len(names):
            raise PublishError("Duplicate remote asset filenames")
        return set(names)

    wheel_name = f"dogopencli-{version}-py3-none-any.whl"
    expected = {
        wheel_name,
        f"dogopencli-{version}.tar.gz",
        "install.sh",
        "SHA256SUMS",
        "RELEASE_NOTES.md",
    }
    if release is not None:
        validate(release)
        if not release["is_draft"]:
            if target == "antcode" and release.get("is_anonymous") is not True:
                raise PublishError(
                    "Published release is not confirmed anonymous; refusing mutation"
                )
            if not expected <= assets(release):
                raise PublishError(
                    "Published release attachments are incomplete; refusing mutation"
                )
            print(f"{tag} already published")
            return

    wheels = list(dist.glob(f"dogopencli-{version}-*.whl"))
    sdist = dist / f"dogopencli-{version}.tar.gz"
    if (
        len(wheels) != 1
        or wheels[0].name != wheel_name
        or not wheels[0].is_file()
        or not sdist.is_file()
    ):
        raise PublishError("Expected exactly one current-version wheel and sdist")
    subjects = (command("git", "log", "-8", "--format=%s", head) or "").strip()
    notes = (
        f"# {tag}\n\nSource-Commit: {head}\n"
        f"Source-URL: {SOURCE_URL}/commit/{head}\n"
        f"Source-Tag: {SOURCE_URL}/tree/{tag}\n\n"
        + (
            "AntCode revision is an artifact-host carrier, not the source commit.\n\n"
            if target == "antcode"
            else "GitHub release targets the source commit.\n\n"
        )
        + f"Recent commit subjects (capped at 8):\n{subjects}\n"
    )
    if release is not None and isinstance(release.get("description"), str):
        notes = release["description"]
    if release is None and target == "github":
        command(
            "gh",
            "release",
            "create",
            tag,
            "--repo",
            project,
            "--target",
            head,
            "--verify-tag",
            "--draft",
            "--title",
            tag,
            "--notes",
            notes,
        )
        release = validate(decode(show()))
    if release is None:
        branch = decode(api("branch", "show", "main", "--json"))
        carrier = (
            branch.get("commit", {}).get("id")
            if isinstance(branch.get("commit"), dict)
            else None
        )
        if not isinstance(carrier, str) or not re.fullmatch(r"[0-9a-f]{40}", carrier):
            raise PublishError("Invalid AntCode main carrier commit")
        release = validate(
            decode(
                api(
                    "release",
                    "create",
                    tag,
                    "--revision",
                    carrier,
                    "--draft",
                    "--anonymous",
                    "--title",
                    tag,
                    "--description",
                    notes,
                    "--json",
                )
            )
        )
        if release["revision"] != carrier:
            raise PublishError("Created release carrier does not match AntCode main")
    carrier = release["revision"]
    if not release["is_draft"]:
        raise PublishError("Release must be a draft")

    existing = assets(release)
    with tempfile.TemporaryDirectory(prefix="dogopencli-release-") as directory:
        temporary = Path(directory)

        provider = target

        def download(name, target):
            if provider == "github":
                command(
                    "gh",
                    "release",
                    "download",
                    tag,
                    "--repo",
                    project,
                    "--pattern",
                    name,
                    "--output",
                    str(target),
                    "--clobber",
                )
            else:
                api(
                    "release", "download", tag, name, "--output", str(target), "--quiet"
                )
            if not target.is_file():
                raise PublishError("Asset download did not produce a file")

        def upload(path):
            if target == "github":
                command("gh", "release", "upload", tag, str(path), "--repo", project)
            else:
                api("release", "upload", tag, str(path), "--quiet")

        sums = []
        wheel_digest = ""
        for local in [wheels[0], sdist]:
            canonical = temporary / local.name
            if local.name not in existing:
                shutil.copyfile(local, canonical)
                upload(canonical)
            # Always hash server bytes, including after an upload.
            download(local.name, canonical)
            if (
                local.name not in existing
                and canonical.read_bytes() != local.read_bytes()
            ):
                raise PublishError(f"Uploaded {local.name} differs from server bytes")
            digest = hashlib.sha256(canonical.read_bytes()).hexdigest()
            sums.append(f"{digest}  {local.name}\n")
            if local.name == wheel_name:
                wheel_digest = digest
        template = (ROOT / "scripts/install-release.sh").read_text(encoding="utf-8")
        host = "github.com" if target == "github" else "code.alipay.com"
        replacements = {
            "@VERSION@": version,
            "@RELEASE_BASE_URL@": f"https://{host}/{project}/releases/download/{tag}",
            "@WHEEL@": wheel_name,
            "@WHEEL_SHA256@": wheel_digest,
        }
        if any(token not in template for token in replacements):
            raise PublishError("Installer template is missing required tokens")
        installer = re.sub(
            r"@(?:VERSION|RELEASE_BASE_URL|WHEEL|WHEEL_SHA256)@",
            lambda match: replacements[match.group()],
            template,
        )
        sums.append(
            f"{hashlib.sha256(installer.encode('utf-8')).hexdigest()}  install.sh\n"
        )
        for name, body in [
            ("install.sh", installer),
            ("SHA256SUMS", "".join(sums)),
            ("RELEASE_NOTES.md", notes),
        ]:
            generated = temporary / name
            generated.write_text(body, encoding="utf-8")
            if name in existing:
                downloaded = temporary / f"existing-{name}"
                download(name, downloaded)
                if generated.read_bytes() != downloaded.read_bytes():
                    raise PublishError(f"Existing {name} differs; refusing overwrite")
            else:
                upload(generated)
                downloaded = temporary / f"uploaded-{name}"
                download(name, downloaded)
                if generated.read_bytes() != downloaded.read_bytes():
                    raise PublishError(f"Uploaded {name} differs from server bytes")
        current = validate(decode(show()))
        if current["revision"] != carrier or not current["is_draft"]:
            raise PublishError("Draft changed during publication")
        if not expected <= assets(current):
            raise PublishError("Release attachments are incomplete")
        if target == "github":
            command("gh", "release", "edit", tag, "--repo", project, "--draft=false")
            finalized = validate(decode(show()))
        else:
            finalized = validate(
                decode(
                    api(
                        "release",
                        "update",
                        tag,
                        "--draft=false",
                        "--anonymous=true",
                        "--json",
                    )
                )
            )
        if (
            finalized["is_draft"]
            or finalized["revision"] != carrier
            or (target == "antcode" and finalized.get("is_anonymous") is not True)
        ):
            raise PublishError("Release finalization was not confirmed")
    print(f"Published {tag}")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--dist", type=Path, default=Path("dist"))
    parser.add_argument("--target", choices=["antcode", "github"], default="antcode")
    parser.add_argument(
        "--project", help="destination namespace/project (provider default if omitted)"
    )
    parser.add_argument("--require-token", action="store_true")
    args = parser.parse_args(argv)
    try:
        project = args.project or (
            "proletariat64/dogopencli"
            if args.target == "github"
            else "pd.pt/dogopencli"
        )
        publish(args.tag, args.dist.resolve(), project, args.require_token, args.target)
    except (PublishError, OSError, KeyError, ValueError):
        # Never print exceptions originating from files or provider responses.
        error = sys.exc_info()[1]
        print(
            str(error) if isinstance(error, PublishError) else "Publication failed",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
