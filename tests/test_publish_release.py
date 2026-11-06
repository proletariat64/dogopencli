"""Release publication contracts; subprocesses are entirely fake and offline."""

import hashlib
import importlib.util
import json
import subprocess
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location(
    "publish_release",
    Path(__file__).resolve().parents[1] / "scripts/publish_release.py",
)
assert SPEC and SPEC.loader
publisher = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(publisher)

HEAD = "a" * 40
CARRIER = "c" * 40
SOURCE_DESCRIPTION = (
    f"Source-Commit: {HEAD}\n"
    f"Source-URL: https://github.com/proletariat64/dogopencli/commit/{HEAD}\n"
    "Source-Tag: https://github.com/proletariat64/dogopencli/tree/v0.1.0\n"
)
TAG = "v0.1.0"
WHEEL = "dogopencli-0.1.0-py3-none-any.whl"
SDIST = "dogopencli-0.1.0.tar.gz"


class FakeCLI:
    def __init__(self):
        self.calls = []
        self.release = None
        self.files = {}
        self.tag_commit = HEAD
        self.local_tag_commit = HEAD
        self.origin = publisher.SOURCE_REMOTE
        self.carrier = CARRIER
        self.dirty = False
        self.show_status = 404
        self.fail_upload = None
        self.hide_assets = False
        self.confirm_anonymous = True

    def draft(self):
        self.release = {
            "id": 12,
            "tag_name": TAG,
            "revision": self.carrier,
            "description": SOURCE_DESCRIPTION,
            "is_draft": True,
            "is_anonymous": False,
            "assets": [],
        }

    def response(self):
        assert self.release is not None
        return dict(
            self.release,
            assets=[
                {"filename": name, "size": len(body), "digest": "", "url": "private"}
                for name, body in self.files.items()
                if not self.hide_assets
            ],
        )

    def __call__(self, args, **kwargs):
        assert kwargs["timeout"] == 180
        assert kwargs["capture_output"] is True
        assert kwargs["check"] is False
        self.calls.append(args)
        status, output, error = 0, "", ""
        if args[0] == "git":
            if args[1] == "status":
                output = " M file" if self.dirty else ""
            elif args[1] == "rev-parse":
                output = HEAD if args[2] == "HEAD" else self.local_tag_commit
            elif args[1] == "remote":
                output = self.origin
            elif args[1] == "ls-remote":
                assert args[3] == publisher.SOURCE_REMOTE
                output = f"{self.tag_commit}\trefs/tags/{TAG}^{{}}\n"
            else:
                assert args[1:] == ("log", "-8", "--format=%s", HEAD)
                output = "feat: release\nfix: sync\n"
        else:
            assert args[0] == "antcode"
            assert args[-2:] == ("--project", "pd.pt/dogopencli")
            group, operation = args[1:3]
            if group == "branch":
                assert operation == "show" and args[3] == "main"
                output = json.dumps({"commit": {"id": self.carrier}})
            elif operation == "show":
                if self.release is None:
                    status, error = 1, f"HTTP {self.show_status}: secret-provider-body"
                else:
                    output = json.dumps(self.response())
            elif operation == "create":
                assert "--draft" in args and "--json" in args
                assert "--anonymous" in args
                assert args[args.index("--revision") + 1] == self.carrier
                self.draft()
                assert self.release is not None
                self.release["is_anonymous"] = True
                self.release["description"] = args[args.index("--description") + 1]
                output = json.dumps(self.response())
                error = "Created release (notice only on stderr)"
            elif operation == "upload":
                path = Path(args[4])
                if path.name == self.fail_upload:
                    status, error = 1, "secret-provider-body token-value"
                else:
                    assert path.name not in self.files, "Never replace remote files"
                    self.files[path.name] = path.read_bytes()
            elif operation == "download":
                Path(args[args.index("--output") + 1]).write_bytes(self.files[args[4]])
            elif operation == "update":
                assert "--draft=false" in args
                assert "--anonymous=true" in args
                assert self.release is not None
                self.release["is_draft"] = False
                if self.confirm_anonymous is None:
                    self.release.pop("is_anonymous", None)
                else:
                    self.release["is_anonymous"] = self.confirm_anonymous
                output = json.dumps(self.response())
            else:
                pytest.fail(f"Unexpected command: {operation}")
        return subprocess.CompletedProcess(args, status, stdout=output, stderr=error)

    @property
    def mutations(self):
        return [
            args
            for args in self.calls
            if args[0] == "antcode"
            and args[1] == "release"
            and args[2] in {"create", "upload", "update"}
        ]


@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.setattr(publisher, "ROOT", tmp_path)
    (tmp_path / "pyproject.toml").write_text('[project]\nversion = "0.1.0"\n')
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts/install-release.sh").write_text(
        '#!/bin/sh\nVERSION="@VERSION@"\nBASE="@RELEASE_BASE_URL@"\n'
        'WHEEL="@WHEEL@"\nSHA="@WHEEL_SHA256@"\n',
        encoding="utf-8",
    )
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / WHEEL).write_bytes(b"local wheel")
    (dist / SDIST).write_bytes(b"local source")
    fake = FakeCLI()
    monkeypatch.setattr(publisher.subprocess, "run", fake)
    monkeypatch.delenv("ANTCODE_SECRET_TOKEN", raising=False)
    monkeypatch.chdir(tmp_path)
    return fake, dist


def run():
    return publisher.main(["--tag", TAG])


def test_cli_not_found_message_allows_creation(setup, monkeypatch):
    fake, _ = setup
    original = fake.__call__

    def run_fake(args, **kwargs):
        result = original(args, **kwargs)
        if args[:3] == ("antcode", "release", "show") and fake.release is None:
            return subprocess.CompletedProcess(
                args,
                1,
                stdout="",
                stderr=(
                    f"antcode: error: failed to get release: release '{TAG}' "
                    "not found in repository 330298081\n"
                ),
            )
        return result

    monkeypatch.setattr(publisher.subprocess, "run", run_fake)
    assert run() == 0


def test_optional_api_fields_can_be_omitted(setup, monkeypatch):
    fake, _ = setup
    original = fake.response

    def response():
        value = original()
        if not value["assets"]:
            value.pop("assets")
        else:
            for asset in value["assets"]:
                asset.pop("digest")
                asset.pop("url")
        return value

    monkeypatch.setattr(fake, "response", response)
    assert run() == 0


def test_happy_path(setup, capsys):
    fake, _ = setup
    assert run() == 0
    assert fake.release["is_draft"] is False
    assert fake.release["is_anonymous"] is True
    assert set(fake.files) == {
        WHEEL,
        SDIST,
        "install.sh",
        "SHA256SUMS",
        "RELEASE_NOTES.md",
    }
    assert len(fake.files["SHA256SUMS"].splitlines()) == 3
    for name in [WHEEL, SDIST, "install.sh"]:
        expected = hashlib.sha256(fake.files[name]).hexdigest()
        assert f"{expected}  {name}\n".encode() in fake.files["SHA256SUMS"]
    assert HEAD.encode() in fake.files["RELEASE_NOTES.md"]
    assert fake.release["revision"] == CARRIER
    assert SOURCE_DESCRIPTION.encode() in fake.files["RELEASE_NOTES.md"]
    assert not any(args[:3] == ("antcode", "tag", "show") for args in fake.calls)
    assert not any(args[:2] == ("git", "push") for args in fake.calls)
    assert b"capped at 8" in fake.files["RELEASE_NOTES.md"]
    assert capsys.readouterr().out == f"Published {TAG}\n"


@pytest.mark.parametrize("existing_metadata", [False, True])
def test_resume_uses_remote_bytes_not_local_rebuild(setup, existing_metadata):
    fake, dist = setup
    if existing_metadata:
        assert run() == 0
        fake.release["is_draft"] = True
    else:
        fake.draft()
        fake.files[WHEEL] = b"canonical wheel from prior build"
    original = dict(fake.files)
    fake.calls.clear()
    (dist / WHEEL).write_bytes(b"new timestamps in rebuilt wheel")
    (dist / SDIST).write_bytes(b"new source timestamps")
    assert run() == 0
    assert all(fake.files[name] == body for name, body in original.items())
    digest = hashlib.sha256(original[WHEEL]).hexdigest()
    assert digest.encode() in fake.files["SHA256SUMS"]
    assert digest.encode() in fake.files["install.sh"]
    assert not any(Path(c[4]).name == WHEEL for c in fake.mutations if c[2] == "upload")


def test_published_duplicate_is_noop_even_without_dist(setup, capsys):
    fake, dist = setup
    assert run() == 0
    fake.calls.clear()
    capsys.readouterr()
    for path in dist.iterdir():
        path.unlink()
    assert run() == 0
    assert fake.mutations == []
    assert "already published" in capsys.readouterr().out


@pytest.mark.parametrize(
    "mismatch", ["version", "local-tag", "remote-tag", "provenance", "dirty", "origin"]
)
def test_identity_checks_prevent_mutations(setup, mismatch):
    fake, _ = setup
    if mismatch == "version":
        assert publisher.main(["--tag", "v0.2.0"]) == 1
    else:
        if mismatch == "remote-tag":
            fake.tag_commit = "b" * 40
        elif mismatch == "local-tag":
            fake.local_tag_commit = "b" * 40
        elif mismatch == "origin":
            fake.origin = "https://example.invalid/dogopencli.git"
        elif mismatch == "provenance":
            fake.draft()
            fake.release["description"] = "Unrelated test release"
        else:
            fake.dirty = True
        assert run() == 1
    assert fake.mutations == []


@pytest.mark.parametrize("status", [401, 403, 404, 500])
def test_only_404_allows_creation(setup, status, capsys):
    fake, _ = setup
    fake.show_status = status
    assert run() == (0 if status == 404 else 1)
    assert bool(fake.mutations) is (status == 404)
    assert "secret-provider-body" not in str(capsys.readouterr())


def test_upload_failure_leaves_draft_and_can_retry(setup, capsys):
    fake, _ = setup
    fake.fail_upload = SDIST
    assert run() == 1
    assert fake.release["is_draft"] is True
    assert set(fake.files) == {WHEEL}
    assert "token-value" not in str(capsys.readouterr())
    fake.fail_upload = None
    assert run() == 0
    assert fake.release["is_draft"] is False


@pytest.mark.parametrize("filename", ["install.sh", "SHA256SUMS", "RELEASE_NOTES.md"])
def test_metadata_mismatch_is_never_overwritten(setup, filename):
    fake, _ = setup
    assert run() == 0
    fake.release["is_draft"] = True
    fake.files[filename] = b"different remote metadata"
    fake.calls.clear()
    assert run() == 1
    assert fake.mutations == []
    assert fake.release["is_draft"] is True
    assert fake.files[filename] == b"different remote metadata"


@pytest.mark.parametrize("anonymous", [False, None, "true", 1])
def test_finalized_private_or_unconfirmed_release_is_not_mutated(
    setup, anonymous, capsys
):
    fake, _ = setup
    assert run() == 0
    if anonymous is None:
        fake.release.pop("is_anonymous")
    else:
        fake.release["is_anonymous"] = anonymous
    fake.calls.clear()
    assert run() == 1
    assert fake.mutations == []
    assert "not confirmed anonymous" in capsys.readouterr().err


@pytest.mark.parametrize(
    "filename", [WHEEL, SDIST, "install.sh", "SHA256SUMS", "RELEASE_NOTES.md"]
)
def test_finalized_incomplete_release_is_not_mutated(setup, filename, capsys):
    fake, _ = setup
    assert run() == 0
    del fake.files[filename]
    fake.calls.clear()
    assert run() == 1
    assert fake.mutations == []
    assert "attachments are incomplete" in capsys.readouterr().err


@pytest.mark.parametrize("anonymous", [False, None])
def test_finalization_requires_explicit_anonymous_confirmation(
    setup, anonymous, capsys
):
    fake, _ = setup
    fake.confirm_anonymous = anonymous
    assert run() == 1
    assert "finalization was not confirmed" in capsys.readouterr().err


def test_legacy_private_draft_becomes_anonymous(setup):
    fake, _ = setup
    fake.draft()
    assert run() == 0
    assert fake.release["is_anonymous"] is True


def test_installer_contains_exact_release_values(setup):
    fake, _ = setup
    assert run() == 0
    digest = hashlib.sha256(fake.files[WHEEL]).hexdigest()
    assert fake.files["install.sh"].decode() == (
        '#!/bin/sh\nVERSION="0.1.0"\n'
        f'BASE="https://code.alipay.com/pd.pt/dogopencli/releases/download/{TAG}"\n'
        f'WHEEL="{WHEEL}"\nSHA="{digest}"\n'
    )


@pytest.mark.parametrize(
    "project",
    [
        "../dogopencli",
        "pd.pt/..",
        "pd.pt/dogopencli/extra",
        "pd.pt/dogopencli\n",
        "pd.pt/dog'pdkb",
        'pd.pt/dog"pdkb',
        "pd.pt/$(id)",
        "pd.pt/dog%2fpdkb",
        "-namespace/project",
        "namespace/",
        "namespace\\project",
    ],
)
def test_unsafe_project_fails_before_commands(setup, project):
    fake, _ = setup
    assert publisher.main(["--tag", TAG, f"--project={project}"]) == 1
    assert fake.calls == []


@pytest.mark.parametrize(
    "version", ["01.1.0", "1.01.0", "1.0.01", "1.0", "1.0.0rc1", "1.0.0\n"]
)
def test_noncanonical_version_fails_before_commands(setup, version):
    fake, dist = setup
    (dist.parent / "pyproject.toml").write_text(
        f"[project]\nversion = {json.dumps(version)}\n"
    )
    assert publisher.main(["--tag", f"v{version}"]) == 1
    assert fake.calls == []


def test_only_universal_wheel_is_accepted(setup):
    fake, dist = setup
    (dist / WHEEL).rename(dist / "dogopencli-0.1.0-cp312-cp312-linux_x86_64.whl")
    assert run() == 1
    assert fake.mutations == []


def test_missing_template_token_prevents_finalization(setup):
    fake, dist = setup
    (dist.parent / "scripts/install-release.sh").write_text("@VERSION@\n")
    assert run() == 1
    assert fake.release["is_draft"] is True
    assert not any(args[2] == "update" for args in fake.mutations)


def test_missing_required_token_prevents_all_commands(setup, capsys):
    fake, _ = setup
    assert publisher.main(["--tag", TAG, "--require-token"]) == 1
    assert fake.calls == []
    assert "ANTCODE_SECRET_TOKEN is required" in capsys.readouterr().err


def test_required_token_present_is_not_printed(setup, monkeypatch, capsys):
    monkeypatch.setenv("ANTCODE_SECRET_TOKEN", "token-value")
    assert publisher.main(["--tag", TAG, "--require-token"]) == 0
    assert "token-value" not in str(capsys.readouterr())


@pytest.mark.parametrize("draft", [True, False])
@pytest.mark.parametrize(
    "description",
    [
        "Unrelated experimental release",
        SOURCE_DESCRIPTION.replace(HEAD, "b" * 40),
        SOURCE_DESCRIPTION + f"Source-Commit: {HEAD}\n",
        SOURCE_DESCRIPTION.replace("Source-Tag:", "Other-Tag:"),
    ],
)
def test_unrelated_release_is_not_resumed_or_accepted(setup, draft, description):
    fake, _ = setup
    assert run() == 0
    fake.release["is_draft"] = draft
    fake.release["description"] = description
    fake.calls.clear()
    assert run() == 1
    assert fake.mutations == []


def test_retry_reuses_carrier_and_notes_when_antcode_main_changes(setup):
    fake, _ = setup
    assert run() == 0
    notes = fake.files["RELEASE_NOTES.md"]
    fake.release["is_draft"] = True
    fake.carrier = "d" * 40
    fake.calls.clear()
    assert run() == 0
    assert fake.release["revision"] == CARRIER
    assert fake.files["RELEASE_NOTES.md"] == notes
    assert not any(args[1:3] == ("branch", "show") for args in fake.calls)


@pytest.mark.parametrize("carrier", [None, "main", "short", 123])
def test_invalid_carrier_prevents_release_creation(setup, carrier):
    fake, _ = setup
    fake.carrier = carrier
    assert run() == 1
    assert fake.mutations == []


def test_missing_github_tag_refuses_publication(setup):
    fake, _ = setup
    fake.tag_commit = ""
    assert run() == 1
    assert fake.mutations == []


def test_incomplete_assets_prevent_finalization(setup):
    fake, _ = setup
    fake.hide_assets = True
    assert run() == 1
    assert fake.release["is_draft"] is True
    assert not any(args[2] == "update" for args in fake.mutations)


@pytest.mark.parametrize(
    "failure", [OSError("token-value"), subprocess.TimeoutExpired("token-value", 180)]
)
def test_command_failures_are_sanitized(setup, monkeypatch, capsys, failure):
    def fail(*args, **kwargs):
        raise failure

    monkeypatch.setattr(publisher.subprocess, "run", fail)
    assert run() == 1
    assert "token-value" not in str(capsys.readouterr())


@pytest.mark.parametrize("output", ["[]", "not json", '{"message":"token-value"}'])
def test_invalid_release_response_fails_closed(setup, monkeypatch, output):
    fake, _ = setup
    original = fake.__call__

    def run_fake(args, **kwargs):
        result = original(args, **kwargs)
        if args[:3] == ("antcode", "release", "show"):
            return subprocess.CompletedProcess(args, 0, stdout=output, stderr="")
        return result

    monkeypatch.setattr(publisher.subprocess, "run", run_fake)
    assert run() == 1
    assert fake.mutations == []


class FakeGitHub(FakeCLI):
    def __call__(self, args, **kwargs):
        if args[0] == "git":
            return super().__call__(args, **kwargs)
        self.calls.append(args)
        assert args[0] == "gh"
        output, status, error = "", 0, ""
        if args[1] == "api":
            assert args[2] == "repos/proletariat64/dogopencli/releases?per_page=100"
            assert "--paginate" in args and "--slurp" in args
            if self.release is None and self.show_status != 404:
                status, error = (
                    1,
                    f"gh: error (HTTP {self.show_status}) secret-provider-body",
                )
            else:
                rows = (
                    []
                    if self.release is None
                    else [
                        dict(
                            self.release,
                            assets=[
                                {"name": name, "size": len(body)}
                                for name, body in self.files.items()
                            ],
                        )
                    ]
                )
                # Include an unrelated first page; drafts may be on later pages.
                output = json.dumps([[{"tag_name": "unrelated"}], rows])
        else:
            assert args[1] == "release"
            assert args[args.index("--repo") + 1] == "proletariat64/dogopencli"
            operation = args[2]
            if operation == "create":
                assert "--draft" in args and "--verify-tag" in args
                assert args[args.index("--target") + 1] == HEAD
                self.release = {
                    "id": 12,
                    "tag_name": TAG,
                    "target_commitish": HEAD,
                    "draft": True,
                    "body": args[args.index("--notes") + 1],
                }
            elif operation == "upload":
                assert "--clobber" not in args
                path = Path(args[4])
                assert path.name not in self.files
                if path.name == self.fail_upload:
                    status, error = 1, "secret-provider-body"
                else:
                    self.files[path.name] = path.read_bytes()
            elif operation == "download":
                name = args[args.index("--pattern") + 1]
                Path(args[args.index("--output") + 1]).write_bytes(self.files[name])
            elif operation == "edit":
                assert "--draft=false" in args
                self.release["draft"] = False
            else:
                pytest.fail(f"Unexpected gh operation: {operation}")
        return subprocess.CompletedProcess(args, status, stdout=output, stderr=error)


@pytest.fixture
def github(setup, monkeypatch):
    fake = FakeGitHub()
    monkeypatch.setattr(publisher.subprocess, "run", fake)
    return fake, setup[1]


def run_github():
    return publisher.main(["--tag", TAG, "--target", "github"])


def test_github_publish_retry_and_installer(github):
    fake, dist = github
    fake.fail_upload = SDIST
    assert run_github() == 1
    assert fake.release["draft"] is True
    wheel = fake.files[WHEEL]
    (dist / WHEEL).write_bytes(b"rebuilt wheel")
    fake.fail_upload = None
    assert run_github() == 0
    assert fake.release["draft"] is False
    assert fake.files[WHEEL] == wheel
    assert (
        f"https://github.com/proletariat64/dogopencli/releases/download/{TAG}".encode()
        in fake.files["install.sh"]
    )
    for name in [WHEEL, SDIST, "install.sh"]:
        assert (
            f"{hashlib.sha256(fake.files[name]).hexdigest()}  {name}\n".encode()
            in fake.files["SHA256SUMS"]
        )
    fake.calls.clear()
    assert run_github() == 0
    assert all(args[0] == "git" or args[1] == "api" for args in fake.calls)


@pytest.mark.parametrize("status", [401, 403, 500])
def test_github_lookup_errors_do_not_create(github, status, capsys):
    fake, _ = github
    fake.show_status = status
    assert run_github() == 1
    assert fake.release is None
    assert "secret-provider-body" not in str(capsys.readouterr())


@pytest.mark.parametrize(
    "field,value", [("body", "unrelated"), ("target_commitish", "b" * 40)]
)
def test_github_identity_mismatch_blocks_retry(github, field, value):
    fake, _ = github
    assert run_github() == 0
    fake.release["draft"] = True
    fake.release[field] = value
    fake.calls.clear()
    assert run_github() == 1
    assert all(args[0] == "git" or args[1] == "api" for args in fake.calls)


def test_github_metadata_is_never_replaced(github):
    fake, _ = github
    assert run_github() == 0
    fake.release["draft"] = True
    fake.files["install.sh"] = b"conflicting installer"
    assert run_github() == 1
    assert fake.release["draft"] is True
    assert fake.files["install.sh"] == b"conflicting installer"


@pytest.mark.parametrize("provider", ["antcode", "github"])
@pytest.mark.parametrize("filename", ["install.sh", "SHA256SUMS", "RELEASE_NOTES.md"])
def test_corrupt_uploaded_metadata_prevents_finalization(
    setup, github, monkeypatch, provider, filename
):
    fake, _ = github if provider == "github" else setup

    def corrupt(args, **kwargs):
        result = fake(args, **kwargs)
        if args[1:3] == ("release", "upload") and Path(args[4]).name == filename:
            fake.files[filename] = b"corrupt server bytes"
        return result

    monkeypatch.setattr(publisher.subprocess, "run", corrupt)
    assert (run_github() if provider == "github" else run()) == 1
    draft_key = "draft" if provider == "github" else "is_draft"
    assert fake.release[draft_key] is True
