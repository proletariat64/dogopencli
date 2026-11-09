"""Offline coverage for stable homepage publication and atomic remote updates."""

import io
import json
import os
import runpy
import shlex
import subprocess
import sys
from pathlib import Path
from urllib import request

import pytest

from scripts import publish_site_release as tool


@pytest.fixture
def release():
    return {
        "tag_name": "v1.2.3",
        "is_draft": False,
        "is_anonymous": True,
        "is_prerelease": False,
        "is_blocked": False,
        "published_at": "2026-11-06T00:00:00Z",
        "assets": [
            {"filename": "install.sh"},
            {"filename": "dogopencli-1.2.3-py3-none-any.whl"},
        ],
    }


@pytest.fixture
def installer():
    return (
        "#!/usr/bin/env bash\nVERSION='1.2.3'\n"
        "WHEEL='dogopencli-1.2.3-py3-none-any.whl'\n"
        f"RELEASE_BASE_URL='{tool.RELEASE_URL}/download/v1.2.3'\n"
    ).encode()


def test_metadata_shape(release, installer):
    assert tool.metadata("v1.2.3", release, installer) == {
        "schema_version": 1,
        "product": "dogopencli",
        "version": "1.2.3",
        "tag": "v1.2.3",
        "channel": "stable",
        "provider": "antcode",
        "installer_url": f"{tool.RELEASE_URL}/download/v1.2.3/install.sh",
        "release_url": tool.RELEASE_URL,
        "auth": "none",
        "published_at": "2026-11-06T00:00:00Z",
    }


@pytest.mark.parametrize("tag", ["1.2.3", "v01.2.3", "v1.2.3-rc1", "v1.2.3;echo bad"])
def test_invalid_tag_never_calls_provider(tag, monkeypatch):
    monkeypatch.setattr(tool, "command", lambda _: pytest.fail("provider called"))
    with pytest.raises(tool.SitePublishError, match="canonical"):
        tool.publish(tag)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("tag_name", "v1.2.4"),
        ("is_draft", True),
        ("is_anonymous", False),
        ("is_prerelease", True),
        ("is_blocked", True),
        ("is_blocked", 0),
        ("assets", []),
        ("assets", ["invalid"]),
        ("published_at", None),
    ],
)
def test_reject_unsafe_release(release, installer, field, value):
    release[field] = value
    with pytest.raises(tool.SitePublishError):
        tool.metadata("v1.2.3", release, installer)


@pytest.mark.parametrize(
    "field", ["is_draft", "is_anonymous", "is_prerelease", "is_blocked"]
)
def test_missing_visibility_flags_fail_closed(release, installer, field):
    del release[field]
    with pytest.raises(tool.SitePublishError):
        tool.metadata("v1.2.3", release, installer)


@pytest.mark.parametrize(
    "body",
    [b"<html>login</html>", b"#!/bin/bash\n", b"\xff"],
)
def test_invalid_installer(release, body):
    with pytest.raises(tool.SitePublishError):
        tool.metadata("v1.2.3", release, body)


@pytest.mark.parametrize(
    "original", [b"1.2.3", b"dogopencli-1.2.3", b"/download/v1.2.3"]
)
def test_installer_must_be_version_bound(release, installer, original):
    with pytest.raises(tool.SitePublishError, match="does not match"):
        tool.metadata("v1.2.3", release, installer.replace(original, b"wrong", 1))


class Response(io.BytesIO):
    status = 200


def test_download_is_bounded(monkeypatch):
    monkeypatch.setattr(
        tool, "urlopen", lambda *a, **kw: Response(b"x" * (1024 * 1024 + 1))
    )
    with pytest.raises(tool.SitePublishError, match="invalid"):
        tool.fetch("https://example.invalid")


def test_download_errors_do_not_expose_provider_message(monkeypatch):
    def fail(*args, **kwargs):
        raise OSError("secret token")

    monkeypatch.setattr(tool, "urlopen", fail)
    with pytest.raises(
        tool.SitePublishError, match="^Anonymous installer download failed$"
    ):
        tool.fetch("https://example.invalid")


def test_command_errors_are_sanitized(monkeypatch):
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *a, **kw: subprocess.CompletedProcess(a, 1, "secret", "credentials"),
    )
    with pytest.raises(
        tool.SitePublishError, match=r"^antcode command failed \(exit 1\)$"
    ):
        tool.command(["antcode", "release", "show"])


def test_publish_transports_only_metadata(release, installer, monkeypatch):
    release["private_provider_field"] = "secret credentials"
    calls = []
    uploaded = []

    def command(arguments):
        calls.append(arguments)
        if arguments[0] == "antcode":
            return json.dumps(release)
        if arguments[:2] == ["poolab", "sync"]:
            uploaded.append(json.loads(Path(arguments[-2]).read_text()))
        return ""

    monkeypatch.setattr(tool, "command", command)
    monkeypatch.setattr(tool, "fetch", lambda _: installer)
    tool.publish("v1.2.3")
    assert uploaded == [tool.metadata("v1.2.3", release, installer)]
    assert calls[0][:4] == ["antcode", "release", "show", "v1.2.3"]
    assert any(
        tool.REMOTE_UPDATE in shlex.split(args[-1])
        for args in calls
        if args[:3] == ["poolab", "terminal", "execute"]
    )
    assert sum(args[:2] == ["poolab", "sync"] for args in calls) == 1
    update = next(
        shlex.split(args[-1])
        for args in calls
        if args[:3] == ["poolab", "terminal", "execute"]
        and tool.REMOTE_UPDATE in shlex.split(args[-1])
    )
    assert update[-2:] == [
        "/home/admin/webserver/site/releases/dogopencli.json",
        "http://poolab-iys595a7znqgza1e.inc.alipay.net/releases/dogopencli.json",
    ]
    assert "secret credentials" not in json.dumps(uploaded) + json.dumps(calls)


def run_remote(tmp_path, monkeypatch, data, previous=None, replace_failure=False):
    stage = tmp_path / "stage"
    stage.mkdir()
    source = stage / "release.json"
    source.write_text(json.dumps(data))
    destination = tmp_path / "site" / "release.json"
    destination.parent.mkdir()
    if previous is not None:
        destination.write_text(json.dumps(previous))
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "remote",
            str(source),
            str(destination),
            "https://example.invalid/release.json",
        ],
    )
    monkeypatch.setattr(
        request, "urlopen", lambda *a, **kw: Response(json.dumps(data).encode())
    )
    if replace_failure:

        def fail(*args):
            raise OSError("replace failed")

        monkeypatch.setattr(os, "replace", fail)
    return destination, stage


def execute_remote(tmp_path):
    program = tmp_path / "remote_update.py"
    program.write_text(tool.REMOTE_UPDATE)
    runpy.run_path(str(program))


def test_remote_atomic_publish_and_readback(tmp_path, monkeypatch, release, installer):
    data = tool.metadata("v1.2.3", release, installer)
    destination, stage = run_remote(tmp_path, monkeypatch, data)
    destination.parent.chmod(0o750)
    execute_remote(tmp_path)
    assert json.loads(destination.read_bytes()) == data
    assert destination.stat().st_mode & 0o777 == 0o644
    assert destination.parent.stat().st_mode & 0o777 == 0o755
    assert not stage.exists()


@pytest.mark.parametrize("preview", [False, True])
def test_remote_downgrade_guard(tmp_path, monkeypatch, release, installer, preview):
    data = tool.metadata("v1.2.3", release, installer)
    previous = {**data, "version": "2.0.0", "tag": "v2.0.0"}
    if preview:
        previous["channel"] = "preview"
    destination, stage = run_remote(tmp_path, monkeypatch, data, previous)
    if preview:
        execute_remote(tmp_path)
        assert json.loads(destination.read_bytes()) == data
    else:
        with pytest.raises(ValueError, match="downgrade"):
            execute_remote(tmp_path)
        assert json.loads(destination.read_bytes()) == previous
    assert not stage.exists()


def test_failed_replace_preserves_existing_metadata(
    tmp_path, monkeypatch, release, installer
):
    data = tool.metadata("v1.2.3", release, installer)
    previous = {**data, "version": "1.0.0", "tag": "v1.0.0"}
    destination, stage = run_remote(
        tmp_path, monkeypatch, data, previous, replace_failure=True
    )
    with pytest.raises(OSError, match="replace failed"):
        execute_remote(tmp_path)
    assert json.loads(destination.read_bytes()) == previous
    assert not list(destination.parent.glob(".release-*"))
    assert not stage.exists()


@pytest.mark.parametrize("existing", [False, True])
@pytest.mark.parametrize("failure", ["mismatch", "timeout", "readback"])
def test_verification_failure_restores_previous_state(
    tmp_path, monkeypatch, release, installer, existing, failure
):
    data = tool.metadata("v1.2.3", release, installer)
    previous = {**data, "version": "1.0.0", "tag": "v1.0.0"} if existing else None
    destination, stage = run_remote(tmp_path, monkeypatch, data, previous)
    old_bytes = (json.dumps(previous, indent=2) + "\n").encode()
    if existing:
        destination.write_bytes(old_bytes)
        destination.chmod(0o640)
    if failure == "mismatch":
        monkeypatch.setattr(request, "urlopen", lambda *a, **kw: Response(b"{}"))
        error, message = ValueError, "HTTP verification failed"
    elif failure == "timeout":

        def timeout(*args, **kwargs):
            raise TimeoutError("HTTP timeout")

        monkeypatch.setattr(request, "urlopen", timeout)
        error, message = TimeoutError, "HTTP timeout"
    else:
        original_read = Path.read_bytes
        reads = 0

        def read_bytes(path):
            nonlocal reads
            if path == destination:
                reads += 1
                if reads == (2 if existing else 1):
                    return b"incorrect readback"
            return original_read(path)

        monkeypatch.setattr(Path, "read_bytes", read_bytes)
        error, message = ValueError, "metadata readback failed"
    with pytest.raises(error, match=message):
        execute_remote(tmp_path)
    if existing:
        assert destination.read_bytes() == old_bytes
        assert destination.stat().st_mode & 0o777 == 0o640
    else:
        assert not destination.exists()
    assert not list(destination.parent.glob(".release-*"))
    assert not stage.exists()


def test_failed_transport_cleans_owned_stage(release, installer, monkeypatch):
    calls = []

    def command(arguments):
        calls.append(arguments)
        if arguments[0] == "antcode":
            return json.dumps(release)
        if arguments[:2] == ["poolab", "sync"]:
            raise tool.SitePublishError("sync failed")
        return ""

    monkeypatch.setattr(tool, "command", command)
    monkeypatch.setattr(tool, "fetch", lambda _: installer)
    with pytest.raises(tool.SitePublishError, match="sync failed"):
        tool.publish("v1.2.3")
    assert "shutil.rmtree" in calls[-1][-1]
    assert not any(
        tool.REMOTE_UPDATE in shlex.split(args[-1])
        for args in calls
        if args[:3] == ["poolab", "terminal", "execute"]
    )


def test_unsafe_release_never_writes_remote(release, installer, monkeypatch):
    release["is_anonymous"] = False
    calls = []

    def command(arguments):
        calls.append(arguments)
        return json.dumps(release)

    monkeypatch.setattr(tool, "command", command)
    monkeypatch.setattr(tool, "fetch", lambda _: installer)
    with pytest.raises(tool.SitePublishError):
        tool.publish("v1.2.3")
    assert len(calls) == 1


@pytest.mark.parametrize(
    "previous", [b"", b"{broken", b"\xff", b"null", b"[]", b'"text"', b"42", b"false"]
)
@pytest.mark.parametrize("verification_fails", [False, True])
def test_remote_repairs_invalid_metadata_with_rollback(
    tmp_path, monkeypatch, release, installer, previous, verification_fails
):
    data = tool.metadata("v1.2.3", release, installer)
    destination, stage = run_remote(tmp_path, monkeypatch, data)
    destination.write_bytes(previous)
    destination.chmod(0o640)
    if verification_fails:
        monkeypatch.setattr(request, "urlopen", lambda *a, **kw: Response(b"{}"))
        with pytest.raises(ValueError, match="HTTP verification failed"):
            execute_remote(tmp_path)
        assert destination.read_bytes() == previous
        assert destination.stat().st_mode & 0o777 == 0o640
    else:
        execute_remote(tmp_path)
        assert json.loads(destination.read_bytes()) == data
        assert destination.stat().st_mode & 0o777 == 0o644
    assert not stage.exists()
    assert not list(destination.parent.glob(".release-*"))


def test_remote_creates_missing_feed_directory(
    tmp_path, monkeypatch, release, installer
):
    data = tool.metadata("v1.2.3", release, installer)
    destination, stage = run_remote(tmp_path, monkeypatch, data)
    destination.parent.rmdir()
    execute_remote(tmp_path)
    assert json.loads(destination.read_bytes()) == data
    assert (destination.parent / ".dogopencli.lock").exists()
    assert not stage.exists()
