"""Migration helpers reuse host and artifact evidence without a second UAT loop."""

import contextlib
import functools
import importlib.util
import json
import os
import shutil
import stat
import subprocess
import sys
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "leaf_migration", ROOT / "tools/leaf-dev/leaf.py"
)
migration = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(migration)


@pytest.fixture
def independent_host(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    source = repo / "src/dogopencli"
    source.mkdir(parents=True)
    (source / "__init__.py").write_text('__version__ = "1.0"\n')
    (repo / "pyproject.toml").write_text(
        '[project]\nversion="1.0"\ndependencies=["duckdb>=1.1"]\n'
        '[project.scripts]\ndogopencli="dogopencli.cli:main"\n'
    )
    (repo / "uv.lock").write_text("version=1\n")
    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(repo),
            "-c",
            "user.name=fixture",
            "-c",
            "user.email=fixture@example.invalid",
            "commit",
            "--allow-empty",
            "-qm",
            "fixture",
        ],
        check=True,
    )
    package = tmp_path / "installed/site-packages/dogopencli"
    shutil.copytree(source, package)
    monkeypatch.setattr(
        migration, "dogopencli", SimpleNamespace(__file__=str(package / "__init__.py"))
    )
    distribution = SimpleNamespace(
        version="1.0",
        requires=["duckdb>=1.1"],
        entry_points=[
            SimpleNamespace(
                name="dogopencli", value="dogopencli.cli:main", group="console_scripts"
            )
        ],
    )
    monkeypatch.setattr(
        migration.importlib.metadata, "distribution", lambda name: distribution
    )
    return repo, package, distribution


def test_host_reuse_binds_payload_metadata_and_distribution_inputs(independent_host):
    repo, package, distribution = independent_host
    first = migration.host_check(repo)
    assert first["state"] == "verified"
    (repo / "leaf_packages/new.leaf").mkdir(parents=True)
    assert migration.host_check(repo)["files_checked"] == first["files_checked"]
    distribution.requires = ["duckdb>=2"]
    with pytest.raises(migration.HelperError, match="metadata"):
        migration.host_check(repo)
    distribution.requires = ["duckdb>=1.1"]
    (package / "retired.py").write_text("# unexpected installed code\n")
    with pytest.raises(migration.HelperError, match="payload"):
        migration.host_check(repo)


def test_host_reuse_rejects_new_uninstalled_source_and_editable(
    independent_host, monkeypatch
):
    repo, package, _ = independent_host
    (repo / "src/dogopencli/new.py").write_text("# not installed\n")
    with pytest.raises(migration.HelperError, match="payload"):
        migration.host_check(repo)
    monkeypatch.setattr(
        migration.dogopencli, "__file__", str(repo / "src/dogopencli/__init__.py")
    )
    with pytest.raises(migration.HelperError, match="source-independent"):
        migration.host_check(repo)


@pytest.fixture
def delivery(tmp_path, monkeypatch):
    source = tmp_path / "source"
    shutil.copytree(ROOT / "tools/leaf-dev/example", source)
    (source / "adapter.py").write_text("""class Adapter:
    def capability(self, parameters):
        raise AssertionError("business inquiry forbidden in delivery smoke")
    def detail_capability(self, parameters):
        raise AssertionError("business inquiry forbidden in delivery smoke")
    def scope(self, parameters):
        raise AssertionError("business inquiry forbidden in delivery smoke")
    def collector(self, capability, transport, scope, *, progress=None):
        raise AssertionError("business inquiry forbidden in delivery smoke")
    def filter(self, records, parameters):
        raise AssertionError("business inquiry forbidden in delivery smoke")
adapter = Adapter()
""")
    output = tmp_path / "delivery"
    result = migration.pack([source], output)
    assert result["packages"] == 1
    return output


@pytest.fixture
def http_server(delivery):
    class QuietHandler(SimpleHTTPRequestHandler):
        requests = []

        def log_message(self, *args):
            pass

        def do_GET(self):
            self.requests.append(self.path)
            super().do_GET()

    server = ThreadingHTTPServer(
        ("127.0.0.1", 0), functools.partial(QuietHandler, directory=str(delivery))
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", QuietHandler.requests
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


@pytest.mark.parametrize("relative_work", [False, True])
def test_http_acceptance_is_checksum_install_uninstall_only(
    delivery, http_server, tmp_path, monkeypatch, relative_work
):
    base, requests = http_server
    work = tmp_path / "smoke"
    if relative_work:
        monkeypatch.chdir(tmp_path)
        work = Path("smoke")
        original = migration.tempfile.TemporaryDirectory

        @contextlib.contextmanager
        def python310_temporary_directory(*args, **kwargs):
            # Python 3.10/3.11 preserve a relative dir argument; 3.12+ make it absolute.
            with original(*args, **kwargs) as directory:
                yield (
                    os.path.relpath(directory)
                    if not Path(kwargs["dir"]).is_absolute()
                    else directory
                )

        monkeypatch.setattr(
            migration.tempfile, "TemporaryDirectory", python310_temporary_directory
        )
    result = migration.http_smoke(delivery, base, work)
    assert result["business_queries"] == 0
    assert result["packages"][0]["install"] and result["packages"][0]["uninstall"]
    assert requests == ["/collection.sample.records.zip"]
    assert list(work.iterdir()) == [work / "http-smoke.json"]
    assert not (tmp_path / "plugins").exists()
    assert json.loads((work / "http-smoke.json").read_text()) == result


def test_changed_delivery_bytes_fail_before_install(
    delivery, http_server, tmp_path, monkeypatch
):
    archive = delivery / "collection.sample.records.zip"
    archive.write_bytes(archive.read_bytes() + b"changed")
    monkeypatch.setattr(
        migration, "cli", lambda *args: pytest.fail("must not install changed ZIP")
    )
    with pytest.raises(migration.HelperError, match="ZIP changed"):
        migration.http_smoke(delivery, http_server[0], tmp_path / "smoke")
    assert not http_server[1]


def test_remote_wrong_checksum_fails_without_local_install(
    delivery, http_server, tmp_path, monkeypatch
):
    monkeypatch.setattr(
        migration,
        "_download",
        lambda url, path: path.write_bytes(b"wrong remote bytes"),
    )
    monkeypatch.setattr(
        migration, "cli", lambda *args: pytest.fail("must not install remote mismatch")
    )
    with pytest.raises(migration.HelperError, match="Remote HTTP ZIP checksum"):
        migration.http_smoke(delivery, http_server[0], tmp_path / "smoke")


@pytest.mark.parametrize("different", ['{"n":true}', '{"n":"1"}', '{"n":1.0}'])
def test_comparison_preserves_json_types(tmp_path, different):
    expected, actual = tmp_path / "expected", tmp_path / "actual"
    expected.write_text('{"n":1}')
    actual.write_text(different)
    with pytest.raises(migration.HelperError, match="values/types"):
        migration.compare(expected, actual, "", "")


def test_comparison_preserves_full_records_decimals_order_and_multiplicity(tmp_path):
    expected, actual = tmp_path / "expected", tmp_path / "actual"
    rows = '[{"v":12345678901234567890.00000000001,"unknown":{"x":null}},{"v":0}]'
    expected.write_text('{"records":' + rows + "}")
    actual.write_text('{"data":' + rows + "}")
    assert migration.compare(expected, actual, "/records", "/data")["rows"] == 2
    actual.write_text(
        '{"data":[{"v":0},{"v":12345678901234567890.00000000001,"unknown":{"x":null}}]}'
    )
    with pytest.raises(migration.HelperError):
        migration.compare(expected, actual, "/records", "/data")
    actual.write_text('{"data":' + rows[:-1] + ',{"v":0}]}')
    with pytest.raises(migration.HelperError):
        migration.compare(expected, actual, "/records", "/data")


def test_capture_keeps_original_private_bytes_and_restores_transport(
    tmp_path, monkeypatch
):
    from dogopencli.cli import main
    from dogopencli.jsonutil import canonical
    from dogopencli.transport.cdp import CdpQueryTransport

    response = SimpleNamespace(body=b'{"sensitive":"private-native-value"}', status=200)
    original = lambda self, request, **kwargs: response  # noqa: E731
    monkeypatch.setattr(CdpQueryTransport, "execute", original)
    transport = object.__new__(CdpQueryTransport)
    transport._capability = SimpleNamespace(contract=SimpleNamespace(encoding="json"))
    request = SimpleNamespace(
        method="POST", path="/query.json", body={"scope": "private-scope"}
    )

    def fake_main(arguments):
        assert arguments[-4:] == [
            "--config-dir",
            str(tmp_path / "config"),
            "--format",
            "json",
        ]
        transport.execute(request)
        print(
            canonical(
                {
                    "data": [{"sensitive": "private-value"}],
                    "meta": {"complete": True},
                    "error": None,
                }
            )
        )
        return 0

    monkeypatch.setattr("dogopencli.cli.main", fake_main)
    private = tmp_path / "private"
    result = migration.capture(
        private, tmp_path / "config", ["collection", "list", "sample.records", "--live"]
    )
    assert (private / "native-0.json").read_bytes() == response.body
    assert stat.S_IMODE(private.stat().st_mode) == 0o700
    assert all(stat.S_IMODE(p.stat().st_mode) == 0o600 for p in private.iterdir())
    assert "private-value" not in json.dumps(result)
    assert result["rows"] == 1
    assert CdpQueryTransport.execute is original
    assert main is not fake_main


def test_batch_handoff_covers_remaining_scope_once(tmp_path):
    path = ROOT / "tools/leaf-dev/batches.json"
    result = migration.batches(path)
    assert (result["packages"], result["actions"]) == (80, 107)
    assert (result["delivered_packages"], result["delivered_actions"]) == (53, 76)
    assert (result["remaining_packages"], result["remaining_actions"]) == (27, 31)
    assert len(result["batches"]) == 24
    plan = json.loads(path.read_text())
    plan["batches"][3]["members"][0] = plan["batches"][2]["members"][0]
    invalid = tmp_path / "duplicate-plan.json"
    invalid.write_text(json.dumps(plan))
    with pytest.raises(migration.HelperError, match="Duplicate leaf"):
        migration.batches(invalid)
    plan["batches"][3]["members"].pop(0)
    invalid.write_text(json.dumps(plan))
    with pytest.raises(migration.HelperError, match="complete scope"):
        migration.batches(invalid)


def test_batch_status_counts_complete_leaves_inside_a_blocked_batch(tmp_path):
    plan = {
        "expected_packages": 2,
        "expected_actions": 3,
        "batches": [
            {
                "id": "B01",
                "issue": 1,
                "status": "blocked",
                "members": [
                    {
                        "identity": "liquidity.example.one",
                        "operations": ["list", "get"],
                        "status": "delivered",
                    },
                    {"identity": "collection.example.two", "operations": ["list"]},
                ],
            }
        ],
    }
    path = tmp_path / "partial-plan.json"
    original = json.dumps(plan)
    path.write_text(original)
    result = migration.batches(path)
    assert (result["delivered_packages"], result["delivered_actions"]) == (1, 2)
    assert (result["remaining_packages"], result["remaining_actions"]) == (1, 1)
    batch = result["batches"][0]
    assert (batch["packages"], batch["actions"]) == (2, 3)
    assert (batch["delivered_packages"], batch["delivered_actions"]) == (1, 2)
    assert batch["status"] == "blocked"
    assert path.read_text() == original

    plan["batches"][0]["status"] = "delivered"
    plan["batches"][0]["members"][1]["status"] = "blocked"
    path.write_text(json.dumps(plan))
    with pytest.raises(migration.HelperError, match="delivered batch"):
        migration.batches(path)


@pytest.mark.parametrize("status", [None, True, [], {}, "HOLD", "partial"])
def test_batch_status_rejects_invalid_member_status(tmp_path, status):
    plan = json.loads((ROOT / "tools/leaf-dev/batches.json").read_text())
    plan["batches"][0]["members"][0]["status"] = status
    path = tmp_path / "invalid-status.json"
    path.write_text(json.dumps(plan))
    with pytest.raises(migration.HelperError, match="leaf delivery status"):
        migration.batches(path)


@pytest.mark.parametrize(
    "pointer",
    [
        "/data/-1",
        "/data/01",
        "/data/+0",
        "/data/1",
        "/data/",
        "/data/~2",
        "/data/" + "9" * 5000,
    ],
    ids=["negative", "leading-zero", "plus", "out-of-range", "empty", "escape", "huge"],
)
def test_compare_rejects_invalid_pointer_with_safe_cli_error(tmp_path, pointer):
    expected, actual = tmp_path / "expected.json", tmp_path / "actual.json"
    expected.write_text('{"data":["must-stay-private"]}')
    actual.write_text(expected.read_text())
    result = subprocess.run(
        [
            sys.executable,
            str(Path(migration.__file__)),
            "compare",
            str(expected),
            str(actual),
            "--expected-pointer",
            pointer,
            "--actual-pointer",
            "/data/0",
        ],
        text=True,
        capture_output=True,
    )
    assert result.returncode == 1
    assert result.stderr == ""
    assert json.loads(result.stdout)["state"] == "failed"
    assert "must-stay-private" not in result.stdout


def test_json_pointer_valid_indices_and_escaped_keys():
    value = {"data": [{"a/b": {"~key": ["correct"]}}]}
    assert migration.select(value, "/data/0/a~1b/~0key/0") == "correct"
    assert migration.select({"": None}, "/") is None
