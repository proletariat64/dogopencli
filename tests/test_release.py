"""Exercise GitHub-only source tagging against disposable Git repositories."""

import subprocess

import pytest

from scripts import release as tool


def git(root, *arguments):
    return subprocess.check_output(
        ["git", "-C", str(root), *arguments], text=True
    ).strip()


@pytest.fixture
def commands():
    return []


@pytest.fixture
def repository(tmp_path, monkeypatch, commands):
    root = tmp_path / "checkout"
    root.mkdir()
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "--bare", "-q", str(remote)], check=True)
    git(root, "init", "-q", "-b", "master")
    git(root, "config", "user.name", "Release Test")
    git(root, "config", "user.email", "release@example.invalid")
    (root / "pyproject.toml").write_text('[project]\nversion = "0.1.0"\n')
    (root / "uv.lock").write_text("version = 1\n")
    (root / "Makefile").write_text(
        "check:\n\t@true\nsmoke:\n\t@true\npublish-release:\n\t@true\n"
        "publish-site-release:\n\t@true\n"
    )
    git(root, "add", ".")
    git(root, "commit", "-qm", "feat: initial platform")
    git(root, "remote", "add", "origin", tool.REMOTE)
    git(root, "push", "-q", str(remote), "master")
    original = tool.run

    def run(arguments, directory):
        commands.append(arguments)
        # Never access a real remote; preserve commands for ownership assertions.
        mapped = [str(remote) if arg == tool.REMOTE else arg for arg in arguments]
        return original(mapped, directory)

    monkeypatch.setattr(tool, "run", run)
    return root, remote, run


def test_release_current_merged_version_and_retry(repository, commands):
    root, remote, _ = repository
    before = {
        name: (root / name).read_bytes() for name in ("pyproject.toml", "uv.lock")
    }
    head = git(root, "rev-parse", "HEAD")
    assert tool.release(root) == "v0.1.0"
    assert git(remote, "rev-parse", "v0.1.0^{commit}") == head
    assert git(root, "cat-file", "-t", "v0.1.0") == "tag"
    assert git(remote, "rev-parse", "master") == head
    assert git(root, "rev-parse", "HEAD") == head
    assert before == {name: (root / name).read_bytes() for name in before}
    assert not any(
        args[:2] in [["git", "commit"], ["git", "add"], ["uv", "lock"]]
        for args in commands
    )
    pushes = [args for args in commands if "push" in args]
    assert pushes == [["git", "push", tool.REMOTE, "refs/tags/v0.1.0"]]
    assert not any("code.alipay.com" in arg for args in commands for arg in args)
    commands.clear()
    assert tool.release(root, retry=True) == "v0.1.0"
    assert not any("push" in args for args in commands)


def test_dry_run_does_not_write_or_fetch(repository, commands, capsys):
    root, _, _ = repository
    (root / "pending.txt").write_text("preserve")
    assert tool.release(root, dry_run=True) == "v0.1.0"
    output = capsys.readouterr().out
    assert "Current merged version: 0.1.0" in output
    assert "Commit working-tree changes first" in output
    assert git(root, "tag", "--list") == ""
    assert not any(
        "fetch" in args or "push" in args or args[0] == "make" for args in commands
    )


@pytest.mark.parametrize("version", ["0.1.1", "0.0.9", "bad", "0.2", "00.2.0"])
def test_version_must_already_equal_project(repository, version):
    with pytest.raises(ValueError, match="VERSION must equal"):
        tool.release(repository[0], target=version)


def test_explicit_current_version(repository):
    assert tool.release(repository[0], target="0.1.0") == "v0.1.0"


@pytest.mark.parametrize(
    "state", ["dirty", "branch", "detached", "ahead", "behind", "origin"]
)
def test_reject_unmerged_or_untrusted_checkout(repository, commands, state):
    root, remote, _ = repository
    if state == "dirty":
        (root / "pending").write_text("keep")
    elif state == "branch":
        git(root, "checkout", "-qb", "feature")
    elif state == "detached":
        git(root, "checkout", "-q", "--detach")
    elif state in {"ahead", "behind"}:
        git(root, "commit", "--allow-empty", "-qm", "feat: unmerged")
        if state == "behind":
            git(root, "push", "-q", str(remote), "master")
            git(root, "reset", "--soft", "HEAD~1")
    else:
        git(
            root,
            "remote",
            "set-url",
            "origin",
            "https://example.invalid/dogopencli.git",
        )
    with pytest.raises((ValueError, RuntimeError)):
        tool.release(root)
    assert git(root, "tag", "--list") == ""
    assert not any("push" in args or args[0] == "make" for args in commands)


@pytest.mark.parametrize("remote_tag", [False, True])
def test_existing_tag_needs_retry(repository, remote_tag):
    root, remote, _ = repository
    git(root, "tag", "v0.1.0")
    if remote_tag:
        git(root, "push", "-q", str(remote), "refs/tags/v0.1.0")
        git(root, "tag", "-d", "v0.1.0")
    with pytest.raises(ValueError, match="RETRY=1"):
        tool.release(root)
    assert tool.release(root, retry=True) == "v0.1.0"


@pytest.mark.parametrize("remote_tag", [False, True])
def test_mismatching_tag_is_never_replaced(repository, remote_tag):
    root, remote, _ = repository
    git(root, "commit", "--allow-empty", "-qm", "feat: other")
    git(root, "tag", "v0.1.0")
    if remote_tag:
        git(root, "push", "-q", str(remote), "refs/tags/v0.1.0")
        git(root, "tag", "-d", "v0.1.0")
    git(root, "reset", "--soft", "HEAD~1")
    with pytest.raises(ValueError, match="tag points elsewhere"):
        tool.release(root, retry=True)


@pytest.mark.parametrize("gate", ["check", "smoke"])
def test_checks_fail_before_any_tag(repository, monkeypatch, gate):
    root, remote, original = repository

    def fail(args, directory):
        if args == ["make", gate]:
            raise RuntimeError("gate failed")
        return original(args, directory)

    monkeypatch.setattr(tool, "run", fail)
    with pytest.raises(RuntimeError, match="gate failed"):
        tool.release(root)
    assert git(root, "tag", "--list") == ""
    assert git(remote, "tag", "--list") == ""


def test_publication_order(repository, commands):
    tool.release(repository[0])
    check = commands.index(["make", "check"])
    smoke = commands.index(["make", "smoke"])
    tag = next(i for i, args in enumerate(commands) if args[:3] == ["git", "tag", "-a"])
    push = next(i for i, args in enumerate(commands) if "push" in args)
    publish = commands.index(
        ["make", "publish-release", "TAG=v0.1.0", "TARGET=antcode"]
    )
    assert check < smoke < tag < push < publish


@pytest.mark.parametrize("failure", ["push", "publish-release"])
def test_failures_resume_same_version(repository, monkeypatch, commands, failure):
    root, _, original = repository

    def fail(args, directory):
        if failure in args:
            raise RuntimeError("unavailable")
        return original(args, directory)

    monkeypatch.setattr(tool, "run", fail)
    with pytest.raises(RuntimeError, match="RETRY=1"):
        tool.release(root)
    if failure != "publish-site-release":
        assert not any(
            args[:2] == ["make", "publish-site-release"] for args in commands
        )
    assert tool.package_version(root) == "0.1.0"
    monkeypatch.setattr(tool, "run", original)
    commands.clear()
    assert tool.release(root, retry=True) == "v0.1.0"
    assert ["make", "publish-release", "TAG=v0.1.0", "TARGET=antcode"] in commands
    assert any("push" in args for args in commands) is (failure == "push")


def test_github_target_skips_antcode_homepage(repository, commands):
    assert tool.release(repository[0], provider="github") == "v0.1.0"
    assert ["make", "publish-release", "TAG=v0.1.0", "TARGET=github"] in commands
    assert not any("publish-site-release" in args for args in commands)
    commands.clear()
    assert tool.release(repository[0], provider="github", retry=True) == "v0.1.0"
    assert not any("push" in args for args in commands)


@pytest.mark.parametrize("gate", ["check", "smoke", "publish-release"])
def test_local_gate_diagnostics_keep_provider_output_private(
    tmp_path, monkeypatch, capsys, gate
):
    monkeypatch.setattr(
        tool.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args[0], 1, stdout="stdout detail\n", stderr="stderr detail\n"
        ),
    )
    with pytest.raises(RuntimeError, match="exit 1"):
        tool.run(["make", gate], tmp_path)
    captured = capsys.readouterr()
    if gate == "publish-release":
        assert captured.out == captured.err == ""
    else:
        assert captured.out == "stdout detail\n"
        assert captured.err == "stderr detail\n"
