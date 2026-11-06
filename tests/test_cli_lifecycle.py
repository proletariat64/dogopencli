"""Lifecycle routing, release integrity and unmanaged-install safeguards."""

import hashlib
from pathlib import Path
from types import SimpleNamespace

import pytest

from dogopencli import cli, lifecycle


def test_management_help_and_dispatch(monkeypatch, capsys):
    assert cli.main(["update", "--help"]) == 0
    assert "--to" in capsys.readouterr().out
    calls = []
    monkeypatch.setattr(
        lifecycle, "execute", lambda action, args: calls.append((action, args)) or 0
    )
    assert cli.main(["update", "--to", "0.6.5"]) == 0
    assert calls[0][0] == "update" and calls[0][1].to == "0.6.5"
    assert cli.main(["uninstall"]) == 0
    assert calls[1][0] == "uninstall"


def test_unmanaged_environment_refuses_deletion(monkeypatch, tmp_path):
    monkeypatch.setattr(lifecycle, "uv_command", lambda *args: str(tmp_path))
    with pytest.raises(ValueError, match="uv-installed"):
        lifecycle.locate()


@pytest.mark.parametrize(
    "provider", ["github.com/proletariat64", "code.alipay.com/pd.pt"]
)
def test_release_update_checks_bytes_and_retains_provider(
    tmp_path, monkeypatch, provider
):
    base = f"https://{provider}/dogopencli/releases/download"
    marker = tmp_path / lifecycle.MARKER
    marker.write_text(base + "/v0.6.4\n")
    monkeypatch.setattr(lifecycle, "installed_version", lambda _: "0.6.4")
    body = b"verified-wheel"
    checksum = hashlib.sha256(body).hexdigest()
    calls = []

    def download(url, maximum):
        assert url.startswith(base + "/v0.6.5/")
        if url.endswith("SHA256SUMS"):
            return f"{checksum}  dogopencli-0.6.5-py3-none-any.whl\n".encode()
        return body

    def install(*args):
        assert "uninstall" not in args
        assert "--no-cache" not in args and "--reinstall" not in args
        assert args[args.index("--reinstall-package") + 1] == "dogopencli"
        assert Path(args[-1].removeprefix("dogopencli @ ")).read_bytes() == body
        calls.append(args)
        marker.unlink()  # uv replaces the old environment/marker
        return ""

    monkeypatch.setattr(lifecycle, "download", download)
    monkeypatch.setattr(lifecycle, "uv_command", install)
    lifecycle.update(tmp_path, to="0.6.5", source=None)
    assert len(calls) == 1
    assert marker.read_text() == base + "/v0.6.5\n"
    monkeypatch.setattr(lifecycle, "download", lambda *args: b"wrong checksum")
    with pytest.raises(ValueError, match="checksum"):
        lifecycle.update(tmp_path, to="0.6.6", source=None)
    assert len(calls) == 1


def test_invalid_update_preserves_environment(tmp_path, monkeypatch):
    monkeypatch.setattr(lifecycle, "installed_version", lambda _: "0.6.4")
    for to, source in [
        (None, None),
        ("0.6.5", "something"),
        ("0.6.3", None),
        ("../", None),
    ]:
        with pytest.raises(ValueError):
            lifecycle.update(tmp_path, to=to, source=source)


def test_provider_error_not_printed(monkeypatch, capsys):
    def fail():
        raise OSError("private-token")

    monkeypatch.setattr(lifecycle, "locate", fail)
    assert lifecycle.execute("uninstall", SimpleNamespace(format="json")) == 1
    assert "private-token" not in capsys.readouterr().out
