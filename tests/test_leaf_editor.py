"""Documentation editing through the localhost HTTP boundary."""

import json
import re
import threading
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from dogopencli.domains import DomainService
from dogopencli.gui import create_server


@pytest.fixture
def editor(tmp_path, monkeypatch):
    from dogopencli.leaves.registry import Registry

    def forbidden(*args, **kwargs):
        raise AssertionError("documentation editing must not activate runtime")

    monkeypatch.setattr(Registry, "scan", forbidden)
    monkeypatch.setattr(Registry, "_load", forbidden)
    folder = tmp_path / "plugins/payment/sample"
    folder.mkdir(parents=True)
    manifest = {
        "domain": "payment",
        "name": "sample",
        "adapter": "adapter.py:adapter",
        "operations": {
            "get": {
                "description": "Read detail",
                "parameters": [],
                "lookup": {"name": "reference", "description": "Native reference"},
                "result_identity": {"fields": ["id"], "description": "Native id"},
            }
        },
        "fields": [{"name": "nativeId", "type": "string", "meaning": "Identifier"}],
        "identity": ["nativeId"],
        "summary": "Original summary",
        "purpose": "Inquiry",
        "identity_description": "Native identity",
        "limitations": [],
        "examples": [{"title": "Example", "command": "payment get sample 1"}],
    }
    (folder / "leaf.json").write_text(json.dumps(manifest))
    (folder / "adapter.py").write_text(
        'raise AssertionError("documentation editing must not execute adapters")\n'
    )
    server = create_server(DomainService(tmp_path / "config.toml"))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_port}"
    try:
        with urlopen(url) as response:
            token = re.search(r"const token='([^']+)'", response.read().decode())[1]
        yield url, token, folder / "leaf.json"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(3)


def read_editor(url):
    with urlopen(url + "/api/leaves/payment/sample") as response:
        return json.load(response)


def write_editor(url, token, payload, action="save", **headers):
    with urlopen(
        Request(
            url + "/api/leaves/payment/sample/" + action,
            data=json.dumps(payload).encode(),
            headers={
                "Content-Type": "application/json",
                "X-Dogopencli-Token": token,
                **headers,
            },
        )
    ) as response:
        return json.load(response)


def test_documentation_preview_and_save_preserve_technical_contract(editor):
    url, token, path = editor
    loaded = read_editor(url)
    original = path.read_bytes()
    assert loaded["manifest"]["summary"] == "Original summary"
    assert loaded["schema"]["type"] == "object"
    loaded["manifest"]["summary"] = "Revised summary"
    preview = write_editor(url, token, loaded, "preview")
    assert "Revised summary" in preview["preview"]
    assert path.read_bytes() == original
    saved = write_editor(url, token, loaded)
    assert saved["manifest"]["summary"] == "Revised summary"
    assert json.loads(path.read_bytes())["identity"] == ["nativeId"]


@pytest.mark.parametrize("declaration", ["lookup", "result_identity"])
def test_get_identity_descriptions_are_consistently_read_only(editor, declaration):
    url, token, path = editor
    loaded = read_editor(url)
    get_schema = loaded["schema"]["properties"]["operations"]["properties"]["get"]
    assert (
        get_schema["properties"][declaration]["properties"]["description"]["readOnly"]
        is True
    )
    original = path.read_bytes()
    loaded["manifest"]["operations"]["get"][declaration]["description"] = "Changed"
    with pytest.raises(HTTPError) as failure:
        write_editor(url, token, loaded)
    assert failure.value.code == 400
    assert json.load(failure.value)["error"]["code"] == "READ_ONLY_FIELD"
    assert path.read_bytes() == original


@pytest.mark.parametrize("change", ["technical", "invalid", "conflict"])
def test_invalid_edits_and_conflicts_preserve_disk(editor, change):
    url, token, path = editor
    loaded = read_editor(url)
    if change == "technical":
        loaded["manifest"]["identity"] = ["otherId"]
    elif change == "invalid":
        loaded["manifest"]["summary"] = 123
    else:
        document = json.loads(path.read_bytes())
        document["purpose"] = "External edit"
        path.write_text(json.dumps(document))
    expected = path.read_bytes()
    with pytest.raises(HTTPError) as error:
        write_editor(url, token, loaded)
    assert error.value.code == (409 if change == "conflict" else 400)
    assert path.read_bytes() == expected


def test_editor_mutations_require_local_token_and_origin(editor):
    url, token, path = editor
    loaded = read_editor(url)
    original = path.read_bytes()
    for headers in ({"X-Dogopencli-Token": "wrong"}, {"Origin": "https://evil.test"}):
        with pytest.raises(HTTPError) as error:
            write_editor(url, token, loaded, **headers)
        assert error.value.code == 403
    assert path.read_bytes() == original


def test_documentation_patch_preserves_large_locked_numbers(editor):
    url, token, path = editor
    manifest = json.loads(path.read_text())
    manifest["operations"]["get"]["parameters"] = [
        {
            "name": "external-number",
            "type": "integer",
            "required": False,
            "default": 9007199254740993,
            "description": "Technical default",
        }
    ]
    path.write_text(json.dumps(manifest))
    loaded = read_editor(url)
    assert (
        loaded["number_labels"]["operations.get.parameters 1.default"]
        == "9007199254740993"
    )
    saved = write_editor(
        url,
        token,
        {"revision": loaded["revision"], "documentation": {"summary": "Prose only"}},
    )
    assert saved["manifest"]["summary"] == "Prose only"
    assert (
        saved["manifest"]["operations"]["get"]["parameters"][0]["default"]
        == 9007199254740993
    )
    with pytest.raises(HTTPError) as failure:
        write_editor(
            url,
            token,
            {"revision": saved["revision"], "documentation": {"identity": ["changed"]}},
        )
    assert failure.value.code == 400


def test_text_help_and_editor_preview_preserve_parameter_rules(editor):
    from dogopencli.leaves.documentation import render_text

    url, token, path = editor
    manifest = json.loads(path.read_text())
    manifest["operations"]["get"]["parameters"] = [
        {
            "name": "kind",
            "type": "string",
            "description": "Native kind",
            "required": True,
            "default": ["normal"],
            "choices": ["normal", "special"],
            "multiple": True,
        }
    ]
    path.write_text(json.dumps(manifest))
    loaded = read_editor(url)
    preview = write_editor(url, token, loaded, "preview")["preview"]
    rendered = render_text(loaded["manifest"])
    for text in (preview, rendered):
        for rule in (
            "required",
            'default=["normal"]',
            "choices=normal|special",
            "repeatable",
        ):
            assert rule in text
