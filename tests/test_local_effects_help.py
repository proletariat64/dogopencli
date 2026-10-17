"""Public help distinguishes local operational writes from production mutation."""

import json

import pytest


@pytest.mark.parametrize(
    "path,network,browser",
    [
        (("domain", "enable"), False, False),
        (("domain", "disable"), False, False),
        (("auth", "check"), True, True),
        (("gui",), True, False),
    ],
)
def test_control_help_discloses_local_writes_without_creating_state(
    run_cli, monkeypatch, tmp_path, path, network, browser
):
    monkeypatch.setenv("DOGOPENCLI_CONFIG", str(tmp_path / "config.toml"))
    code, out, error = run_cli([*path, "--help"])
    assert code == 0 and error == ""
    document = json.loads(out)["data"]
    assert document["effects"] == {
        "mutates": True,
        "network": network,
        "browser_required": browser,
        "destructive": False,
    }
    assert any("local" in text.lower() for text in document["constraints"])
    assert any("production" in text.lower() for text in document["constraints"])
    assert list(tmp_path.iterdir()) == []
