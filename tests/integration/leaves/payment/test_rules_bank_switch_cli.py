"""Installed bank-switch source trees preserve same-branch filter semantics."""

from copy import deepcopy
from decimal import Decimal
from pathlib import Path
from zipfile import ZipFile

import pytest
from integration.fake_cdp import FakeBrowser

from dogopencli.browser import cdp
from dogopencli.jsonutil import parse

ROOT = Path(__file__).resolve().parents[4]
LEAF = "rules.bank_switch"
REQUIREMENTS = "fundNavigationNodeSwitchRequirementVOList"


@pytest.fixture(params=["directory"])
def installed(request, run_cli, tmp_path, monkeypatch):
    config = tmp_path / "config"
    config.mkdir()
    (config / "config.toml").write_text(
        f'[auth]\nprofile = "{tmp_path / "chrome"}"\ncdp_url = "http://127.0.0.1:9222"\n'
    )
    monkeypatch.setenv("DOGOPENCLI_CONFIG_DIR", str(config))
    for key in (
        "DOGOPENCLI_CONFIG",
        "DOGOPENCLI_CHROME_CDP_URL",
        "DOGOPENCLI_CHROME_PROFILE",
    ):
        monkeypatch.delenv(key, raising=False)
    browser = FakeBrowser(
        href="https://ifundcontrol.alipay.com/productOperation/paymentProductManagement/"
        "bankSwitchOperation/bankSwitchManage"
    )
    cdp.set_transport_factory(browser.transport)

    def cli(action, *args, code=0):
        result, output, error = run_cli(["payment", action, LEAF, *args])
        assert result == code, output + error
        return parse(output)

    try:
        package = ROOT / "leaf_packages/payment" / LEAF
        if request.param == "zip":
            archive_path = tmp_path / "candidate.zip"
            with ZipFile(archive_path, "w") as archive:
                for path in sorted(package.rglob("*")):
                    if path.is_file() and "__pycache__" not in path.parts:
                        archive.write(path, path.relative_to(package))
            package = archive_path
        result, output, error = run_cli(["plugins", "install", str(package)])
        assert result == 0, output + error
        yield cli, browser, config
    finally:
        cdp.set_transport_factory(None)


def target(account="TARGET", network="ACH"):
    return {"targetNodeCode": account, "clearingNetworkList": [network]}


def rule(status="ON", targets=None):
    return {
        "ruleId": "RULE",
        "status": status,
        "version": "001",
        "ratioList": [
            {"targetNodeInfoList": [target()] if targets is None else targets}
        ],
    }


def row(identity="SOURCE"):
    return {
        "switchNodeCode": identity,
        "extension": [None, False, 0, "", Decimal("0.123456789012345678901")],
        REQUIREMENTS: [
            {
                "switchBankAccount": identity,
                "switchClearingNetwork": "NET",
                "switchRuleVOList": [
                    rule("OFF"),
                    rule("ON", [target("TARGET", "WIRE"), target("OTHER", "ACH")]),
                ],
            },
            {
                "switchClearingNetwork": "OTHER-NET",
                "switchRuleVOList": [rule("ON")],
            },
            {"switchClearingNetwork": "EMPTY-NET", "switchRuleVOList": None},
        ],
    }


def reply(rows, total=None):
    return {
        "status": 200,
        "body": {
            "success": True,
            "data": {
                "businessDataList": rows,
                "pageNo": 0,
                "pageSize": 1000,
                "totalCount": len(rows) if total is None else total,
                "totalPageNo": 0,
            },
        },
    }


@pytest.mark.parametrize("installed", ["directory", "zip"], indirect=True)
def test_native_full_tree_live_refresh_offline_and_closed_query(installed):
    cli, browser, config = installed
    before = sorted(p.relative_to(config) for p in config.rglob("*") if p.is_file())
    cli("list", "--help")
    cli("describe")
    assert not browser.transports
    assert before == sorted(
        p.relative_to(config) for p in config.rglob("*") if p.is_file()
    )
    native = [row("2"), row("10"), {"switchNodeCode": "30", REQUIREMENTS: None}]
    browser.business_script.append(reply(native))
    live = cli("list", "--live", "--require-complete", "--limit", "0")
    assert live["data"] == sorted(native, key=lambda item: item["switchNodeCode"])
    assert live["meta"]["complete"] is True
    assert not (config / "leaf-cache.sqlite3").exists()
    browser.business_script.append(reply(native))
    saved = cli("refresh", "--require-complete")
    assert saved["meta"]["published"] is True
    calls = len(browser.business_requests)
    assert cli("list", "--limit", "0")["data"] == live["data"]
    assert len(browser.business_requests) == calls
    browser.business_script.append(reply([row("NEW")]))
    cli("list", "--live", "--require-complete")
    assert cli("list", "--limit", "0")["data"] == live["data"]
    assert browser.business_requests == [{"pageNo": 0, "pageSize": 1000}] * 3
    expressions = [
        e for t in browser.transports for e in t.expressions if "fetch(" in e
    ]
    assert all(
        "https://ifundcontrolprodops.alipay.com/api/fundNavigation/nodeSwitch/query"
        in expression
        and 'method: "GET"' in expression
        and "pageNo" in expression
        and "pageSize" in expression
        for expression in expressions
    )
    calls = len(browser.business_requests)
    cli("list", "--live", "--page-size", "20", code=2)
    cli("get", code=2)
    assert len(browser.business_requests) == calls


@pytest.mark.parametrize(
    ("flags", "expected"),
    [
        (
            [
                "--source-network",
                "NET",
                "--status",
                "ON",
                "--target-account",
                "TARGET",
                "--target-network",
                "ACH",
            ],
            False,
        ),
        (
            [
                "--source-network",
                "NET",
                "--status",
                "ON",
                "--target-account",
                "TARGET",
                "--target-network",
                "WIRE",
            ],
            True,
        ),
        (
            ["--source-network", "NET", "--status", "OFF", "--target-network", "WIRE"],
            False,
        ),
        (["--source-network", "OTHER-NET", "--status", "OFF"], False),
        (["--source-network", "EMPTY-NET"], False),
        (["--source-network", "NET"], True),
        (
            [
                "--source-account",
                "SOURCE",
                "--source-network",
                "NET",
                "--status",
                "OFF",
                "--target-account",
                "TARGET",
                "--target-network",
                "ACH",
            ],
            True,
        ),
        (["--source-account", "MISSING", "--source-account", "SOURCE"], True),
        (["--target-network", "A", "--target-network", "WIRE"], True),
        (["--source-account", "source"], False),
        (["--source-account", " SOURCE "], False),
        (["--target-network", "ACH,WIRE"], False),
    ],
)
def test_correlated_filters_select_entire_source_without_pruning(
    installed, flags, expected
):
    cli, browser, _ = installed
    native = row()
    browser.business_script.append(reply([native]))
    cli("refresh", "--require-complete")
    assert cli("list", *flags)["data"] == ([native] if expected else [])
    browser.business_script.append(reply([native]))
    assert cli("list", "--live", "--require-complete", *flags)["data"] == (
        [native] if expected else []
    )
    assert browser.business_requests == [{"pageNo": 0, "pageSize": 1000}] * 2


def test_literal_arrays_empty_nodes_and_window_order(installed):
    cli, browser, _ = installed
    first, second = row("2"), row("10")
    first[REQUIREMENTS][0]["switchRuleVOList"] = [rule("ON", [target("*", "A,B")])]
    empty = {"switchNodeCode": "30", REQUIREMENTS: []}
    browser.business_script.append(reply([first, second, empty]))
    cli("refresh", "--require-complete")
    assert cli("list", "--source-account", "30")["data"] == [empty]
    assert cli("list", "--target-account", "*", "--target-network", "A,B")["data"] == [
        first
    ]
    assert cli("list", "--target-account", "*", "--target-network", "A")["data"] == []
    assert cli(
        "list",
        "--source-network",
        "NET",
        "--offset",
        "1",
        "--limit",
        "1",
        "--fields",
        "switchNodeCode",
    )["data"] == [{"switchNodeCode": "2"}]


@pytest.mark.parametrize(
    "flag",
    ["source-account", "source-network", "status", "target-account", "target-network"],
)
def test_blank_filters_reject_before_query(installed, flag):
    cli, browser, _ = installed
    cli("list", "--live", "--" + flag, " ", code=2)
    assert not browser.business_requests


@pytest.mark.parametrize(
    "failure",
    [
        "refusal",
        "success-type",
        "rows",
        "identity",
        "page",
        "size",
        "total",
        "page-count",
        "gap",
        "capacity",
        "duplicate",
        "requirements",
        "rules",
        "ratios",
        "targets",
    ],
)
def test_bad_acquisition_preserves_previous_snapshot(installed, failure):
    cli, browser, _ = installed
    native = [row()]
    browser.business_script.append(reply(native))
    cli("refresh", "--require-complete")
    before = cli("list", "--limit", "0")
    response = reply(deepcopy(native))
    data = response["body"]["data"]
    if failure == "refusal":
        response["body"]["success"] = False
    elif failure == "success-type":
        response["body"]["success"] = "true"
    elif failure == "rows":
        data["businessDataList"] = None
    elif failure == "identity":
        data["businessDataList"][0]["switchNodeCode"] = 1
    elif failure in {"page", "size", "total", "page-count", "gap", "capacity"}:
        field, value = {
            "page": ("pageNo", 1),
            "size": ("pageSize", 10),
            "total": ("totalCount", True),
            "page-count": ("totalPageNo", None),
            "gap": ("totalCount", 2),
            "capacity": ("totalCount", 1001),
        }[failure]
        data[field] = value
    elif failure == "duplicate":
        data["businessDataList"].append(deepcopy(native[0]))
        data["totalCount"] = 2
    else:
        source = data["businessDataList"][0]
        requirement = source[REQUIREMENTS][0]
        child = requirement["switchRuleVOList"][0]
        if failure == "requirements":
            source[REQUIREMENTS] = {}
        elif failure == "rules":
            requirement["switchRuleVOList"] = [None]
        elif failure == "ratios":
            child["ratioList"] = "invalid"
        else:
            child["ratioList"][0]["targetNodeInfoList"] = [False]
    browser.business_script.append(response)
    assert cli("refresh", "--require-complete", code=1)["data"] is None
    after = cli("list", "--limit", "0")
    assert after["data"] == before["data"]
    assert after["meta"]["fetched_at"] == before["meta"]["fetched_at"]
