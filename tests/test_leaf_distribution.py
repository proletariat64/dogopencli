"""Installed-artifact acceptance; opt in with both built artifact paths."""

import ast
import hashlib
import json
import os
import shutil
import subprocess
import tarfile
import venv
import zipfile
from pathlib import Path

import pytest

RETIRED = (
    "plugins",
    "catalog",
    "describe",
    "snapshot",
    "cached_query",
    "handler_contract",
)
PILOTS = (
    ("collection", "cost"),
    ("liquidity", "reference.entities"),
    ("payment", "sla.baselines"),
    ("fx", "trade"),
)
ARTIFACTS = ("DOGOPENCLI_TEST_WHEEL", "DOGOPENCLI_TEST_SDIST")
pytestmark = pytest.mark.skipif(
    not all(os.environ.get(name) for name in ARTIFACTS),
    reason=("Build artifacts; set DOGOPENCLI_TEST_WHEEL and DOGOPENCLI_TEST_SDIST."),
)


@pytest.fixture(params=ARTIFACTS, ids=("wheel", "sdist"))
def artifact(request):
    return Path(os.environ[request.param]).resolve(strict=True)


def test_distributions_exclude_retired_runtime_and_imports(artifact):
    if artifact.suffix == ".whl":
        with zipfile.ZipFile(artifact) as archive:
            contents = {name: archive.read(name) for name in archive.namelist()}
    else:
        with tarfile.open(artifact) as archive:
            contents = {
                member.name: archive.extractfile(member).read()
                for member in archive.getmembers()
                if member.isfile()
            }
    for name, source in contents.items():
        parts = Path(name).parts
        if "dogopencli" not in parts:
            continue
        relative = parts[parts.index("dogopencli") + 1 :]
        assert not relative or relative[0].removesuffix(".py") not in RETIRED, name
        if not name.endswith(".py"):
            continue
        for node in ast.walk(ast.parse(source, filename=name)):
            modules = []
            if isinstance(node, ast.Import):
                modules = [item.name for item in node.names]
            elif isinstance(node, ast.ImportFrom):
                prefix = ["dogopencli", *relative[:-1]]
                if node.level:
                    prefix = prefix[: len(prefix) - node.level + 1]
                    owner = ".".join([*prefix, *(node.module or "").split(".")]).rstrip(
                        "."
                    )
                else:
                    owner = node.module or ""
                modules = [owner, *(f"{owner}.{item.name}" for item in node.names)]
            for module in modules:
                assert not any(
                    module == f"dogopencli.{old}"
                    or module.startswith(f"dogopencli.{old}.")
                    for old in RETIRED
                ), (name, module)
    for domain, leaf in PILOTS:
        assert any(
            name.endswith(f"dogopencli/leaf_packages/{domain}/{leaf}/adapter.py")
            for name in contents
        )


@pytest.fixture
def installed(artifact, tmp_path):
    environment = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(("PYTHON", "DOGOPENCLI_", "DISTRIBUTION_"))
    }
    environment["UV_CACHE_DIR"] = os.environ.get(
        "UV_CACHE_DIR", str(tmp_path / "uv-cache")
    )
    environment["XDG_CACHE_HOME"] = str(tmp_path / "cache")
    environment["DOGOPENCLI_CONFIG"] = str(tmp_path / "state/config.toml")
    environment["DISTRIBUTION_REPORT"] = str(tmp_path / "report.json")
    environment_path = tmp_path / "environment"
    venv.EnvBuilder(with_pip=False).create(environment_path)
    python = environment_path / "bin/python"
    install = subprocess.run(
        ["uv", "pip", "install", "--python", str(python), str(artifact)],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert install.returncode == 0, install.stdout + install.stderr
    assert (
        "include-system-site-packages = false"
        in (environment_path / "pyvenv.cfg").read_text()
    )
    harness = tmp_path / "driver.py"
    shutil.copyfile(Path(__file__).parent / "support/distribution_harness.py", harness)

    def call(*arguments, response=None, auth_required=False):
        process_environment = dict(environment)
        if response is not None:
            process_environment["DISTRIBUTION_RESPONSE"] = json.dumps(response)
        if auth_required:
            process_environment["DISTRIBUTION_AUTH_REQUIRED"] = "1"
        result = subprocess.run(
            [str(python), "-I", str(harness), *arguments],
            cwd=tmp_path,
            env=process_environment,
            capture_output=True,
            text=True,
            check=False,
        )
        report = json.loads(Path(environment["DISTRIBUTION_REPORT"]).read_text())
        checkout = Path(__file__).resolve().parents[1]
        assert not any(
            Path(path).resolve().is_relative_to(checkout)
            for path in report["sys_path"]
            if path
        ), report
        assert report["modules"], result.stderr
        return result, report

    def success(*arguments, **kwargs):
        result, report = call(*arguments, **kwargs)
        assert result.returncode == 0, result.stdout + result.stderr
        return json.loads(result.stdout), report

    # Discovery and help must remain usable before state or adapters exist.
    document, _ = success("plugins", "list")
    assert all(f"{domain}.{leaf}" in json.dumps(document) for domain, leaf in PILOTS)
    assert not (tmp_path / "state").exists()
    success("plugins", "install", "--help")
    root = tmp_path / "state"
    root.mkdir()
    (root / "config.toml").write_text(
        '[auth]\nprofile = "'
        + str(root / "chrome")
        + '"\ncdp_url = "http://127.0.0.1:54396"\n'
    )
    for domain, leaf in PILOTS:
        success("plugins", "install", f"bundled:{domain}.{leaf}")
        assert (root / "plugins" / domain / leaf / "adapter.py").is_file()
    return call, success, root


def _page(domain, rows):
    if domain == "liquidity":
        body = {
            "resultFlag": True,
            "count": len(rows),
            "result": {"entityMaintVOList": rows},
        }
    elif domain == "fx":
        body = {
            "success": True,
            "result": {
                "success": True,
                "value": {
                    "items": rows,
                    "totalCount": len(rows),
                    "currentPage": 0,
                    "pageSize": 50,
                },
            },
        }
    else:
        body = {
            "success": True,
            "resultDataList": rows,
            "totalCount": len(rows),
            "pageNo": 0,
            "pageSize": 1000 if domain == "collection" else 5000,
        }
    return {"status": 200, "body": body}


def test_all_installed_pilots_execute_without_retired_runtime(installed):
    call, success, root = installed
    rows_by_domain = {
        "collection": [
            {
                "itemId": "COST-1",
                "itemType": "FUND_IN_CHANNEL_TRANS_FEE",
                "fee": "0.1000",
            }
        ],
        "liquidity": [{"instId": "ENTITY-1", "instName": "Synthetic institution"}],
        "payment": [{"id": "SLA-1", "status": "ACTIVE", "nativeAmount": "0.1000"}],
        "fx": [{"uniqueId": "TRADE-1", "amount": "0.1234567890123456789"}],
    }
    for domain, leaf in PILOTS:
        success(domain, "list", leaf, "--help")
        described, report = success(domain, "describe", leaf)
        assert described["data"]["id"] == f"{domain}.{leaf}"
        assert report["requests"] == []
        editor, _ = success("__editor__", domain, leaf)
        assert editor["manifest"]["name"] == leaf
        assert editor["gui_port"] > 0
        success("domain", "disable", domain)
        disabled, report = call(domain, "list", leaf, "--live")
        assert disabled.returncode == 1
        assert json.loads(disabled.stdout)["error"]["code"] == "DOMAIN_DISABLED"
        assert report["requests"] == []
        success("domain", "enable", domain)
        unauthenticated, report = call(
            domain, "list", leaf, "--live", auth_required=True
        )
        assert unauthenticated.returncode == 1, unauthenticated.stdout
        assert json.loads(unauthenticated.stdout)["error"]["code"] == "AUTH_REQUIRED"
        assert report["requests"] == []
        success("auth", "check", "--domain", domain)
        rows = rows_by_domain[domain]
        response = _page(domain, rows)
        live, report = success(domain, "list", leaf, "--live", response=response)
        assert live["data"] == rows
        assert len(report["requests"]) == 1
        missing, report = call(domain, "list", leaf)
        assert missing.returncode == 1
        assert json.loads(missing.stdout)["error"]["code"] == "CACHE_MISS"
        assert report["requests"] == []
        refreshed, _ = success(domain, "refresh", leaf, response=response)
        assert refreshed["meta"]["published"] is True
        offline, report = success(domain, "list", leaf)
        assert offline["data"] == rows
        assert report["requests"] == []
        if domain == "fx":
            assert offline["meta"]["complete"] is False
            assert offline["meta"]["unique_count"] is None
            assert {"IDENTITY_UNPROVEN", "TOTAL_SEMANTICS_UNPROVEN"} <= set(
                offline["meta"]["reasons"]
            )
        if domain == "payment":
            filtered, _ = success(domain, "list", leaf, "--status", "ACTIVE")
            assert filtered["data"] == rows
            detail = {"id": "SLA-1", "detailOnly": "native"}
            result, report = success(
                domain,
                "get",
                leaf,
                "SLA-1",
                response={"body": {"success": True, "resultData": detail}},
            )
            assert result["data"] == detail
            assert report["requests"] == [{"slaBaselineId": "SLA-1"}]
    assert (root / "leaf-cache.sqlite3").is_file()
    dataset = root / "duckdog.duckdb"
    assert dataset.is_file()
    retained_digest = hashlib.sha256(dataset.read_bytes()).hexdigest()
    for domain, leaf in PILOTS:
        removed, _ = success("plugins", "uninstall", f"{domain}.{leaf}")
        assert removed["data"]["data_retained"] is True
        assert not (root / "plugins" / domain / leaf).exists()
        assert hashlib.sha256(dataset.read_bytes()).hexdigest() == retained_digest
