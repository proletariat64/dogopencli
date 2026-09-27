"""Payment rule inquiries through public CLI, fake CDP and real SQLite."""

import pytest
from test_sla_cli_sit import sla_setup  # noqa: F401


@pytest.fixture
def setup(sla_setup):  # noqa: F811
    with (sla_setup.tmp_path / "config.toml").open("a") as file:
        for slug in ("same_bank_transfer", "cost_reduction", "retry", "bank_switch"):
            file.write(f'\n[sources.payment_rules_{slug}]\nkind = "cdp"\n')
    return sla_setup


def page(rows, slug="same-bank-transfer", **changes):
    bank = slug == "same-bank-transfer"
    data = {
        "pageNum" if bank else "pageNo": 1 if bank else 0,
        "pageSize": 1000,
        "totalCount": len(rows),
        "totalPages" if bank else "totalPageNo": (1 if rows else 0) if bank else 0,
        "payoutBookDecisionRuleVOList" if bank else "businessDataList": rows,
        **({"success": True} if bank else {}),
        **changes,
    }
    return {
        "status": 200,
        "body": {"success": True, "resultObj" if bank else "data": data},
    }


def refresh(run_cli, slug="same-bank-transfer"):
    return run_cli(["refresh", "payment", "rules", slug])


def listing(run_cli, slug="same-bank-transfer", *flags):
    return run_cli(["payment", "rules", slug, "list", *flags])


def test_same_bank_refresh_offline_preserves_integer_ids(run_cli, envelope, setup):
    rows = [
        {"ruleId": 9007199254740993, "debitInstId": "BANK", "ruleStatus": "ON"},
        {"ruleId": 2, "debitInstId": "OTHER", "future": {"amount": "0.00000001"}},
    ]
    setup.state.business_script.append(page(rows))
    code, out, _ = refresh(run_cli)
    assert code == 0, out
    assert setup.state.business_requests == [{"pageNum": 1, "pageSize": 1000}]
    setup.state.running = False
    code, out, _ = listing(run_cli)
    assert code == 0, out
    assert envelope(out)["data"] == list(reversed(rows))
    assert envelope(out)["meta"]["complete"] is True


def test_cost_reduction_array_members_and_scalar_values_are_distinct(
    run_cli, envelope, setup
):
    rows = [
        {
            "groupId": "20",
            "ruleName": "Exact",
            "legalEntity": ["A", "B"],
            "needObo": ["Y"],
            "creditCurrency": "USD,EUR",
        },
        {
            "groupId": "001",
            "ruleName": "exact",
            "legalEntity": ["A,B"],
            "needObo": ["N"],
            "creditCurrency": "USD",
        },
    ]
    setup.state.business_script.append(page(rows, "cost-reduction"))
    code, out, _ = refresh(run_cli, "cost-reduction")
    assert code == 0, out
    assert envelope(
        listing(run_cli, "cost-reduction", "--entity", "A", "--obo", "Y")[1]
    )["data"] == [rows[0]]
    assert envelope(listing(run_cli, "cost-reduction", "--entity", "A,B")[1])[
        "data"
    ] == [rows[1]]
    assert envelope(listing(run_cli, "cost-reduction", "--currency", "USD")[1])[
        "data"
    ] == [rows[1]]
    assert envelope(listing(run_cli, "cost-reduction", "--name", "Exact")[1])[
        "data"
    ] == [rows[0]]


def test_retry_filters_keep_modes_and_account_members_separate(
    run_cli, envelope, setup
):
    rows = [
        {
            "ruleId": "02",
            "debtorAccountNoList": ["A", "B"],
            "communicationMode": "SYNC",
            "integrationMode": "API",
        },
        {
            "ruleId": "1",
            "debtorAccountNoList": ["A,B"],
            "communicationMode": "ASYNC",
            "integrationMode": "API",
        },
    ]
    setup.state.business_script.append(page(rows, "retry"))
    code, out, _ = refresh(run_cli, "retry")
    assert code == 0, out
    result = listing(
        run_cli,
        "retry",
        "--bank-account",
        "A",
        "--communication-mode",
        "SYNC",
        "--integration-mode",
        "API",
    )
    assert envelope(result[1])["data"] == [rows[0]]
    assert setup.state.business_requests == [{"pageNo": 0, "pageSize": 1000}]


def bank_row(identity="SOURCE", *, requirements=None):
    return {
        "switchNodeCode": identity,
        "fundNavigationNodeSwitchRequirementVOList": requirements
        or [
            {
                "requirementId": "REQ",
                "switchBankAccount": identity,
                "switchClearingNetwork": "NET",
                "switchRuleVOList": [
                    {
                        "ruleId": "OLD",
                        "version": "1",
                        "status": "OFF",
                        "ratioList": [
                            {
                                "targetNodeInfoList": [
                                    {
                                        "targetNodeCode": "TARGET",
                                        "clearingNetworkList": ["ACH"],
                                    }
                                ]
                            }
                        ],
                    },
                    {
                        "ruleId": "NEW",
                        "version": "2",
                        "status": "ON",
                        "ratioList": [
                            {
                                "targetNodeInfoList": [
                                    {
                                        "targetNodeCode": "TARGET",
                                        "clearingNetworkList": ["WIRE"],
                                    },
                                    {
                                        "targetNodeCode": "OTHER",
                                        "clearingNetworkList": ["ACH"],
                                    },
                                ]
                            }
                        ],
                    },
                ],
            },
        ],
    }


def test_bank_switch_correlates_rule_and_target_without_trimming_children(
    run_cli, envelope, setup
):
    row = bank_row()
    setup.state.business_script.append(page([row], "bank-switch"))
    code, out, _ = refresh(run_cli, "bank-switch")
    assert code == 0, out
    base = [
        "--source-account",
        "SOURCE",
        "--source-network",
        "NET",
        "--status",
        "ON",
        "--target-account",
        "TARGET",
    ]
    assert (
        envelope(listing(run_cli, "bank-switch", *base, "--target-network", "ACH")[1])[
            "data"
        ]
        == []
    )
    assert envelope(
        listing(run_cli, "bank-switch", *base, "--target-network", "WIRE")[1]
    )["data"] == [row]
    assert envelope(
        listing(run_cli, "bank-switch", "--status", "OFF", "--target-network", "ACH")[1]
    )["data"] == [row]


def test_bank_describe_explains_nested_correlation_and_no_flattening(run_cli, envelope):
    code, out, _ = run_cli(["describe", "payment", "rules", "bank-switch", "list"])
    assert code == 0, out
    doc = envelope(out)
    props = doc["data_schema"]["items"]["properties"]
    assert "status" not in props
    assert "fundNavigationNodeSwitchRequirementVOList" in props
    guide = str(doc["read_guide"])
    assert "same rule" in guide and "same target" in guide
    assert "entire" in guide


SLUGS = ("same-bank-transfer", "cost-reduction", "retry", "bank-switch")
IDENTITIES = {
    "same-bank-transfer": "ruleId",
    "cost-reduction": "groupId",
    "retry": "ruleId",
    "bank-switch": "switchNodeCode",
}
FILTER_CASES = [
    ("same-bank-transfer", "bank", "debitInstId", False),
    ("same-bank-transfer", "status", "ruleStatus", False),
    ("cost-reduction", "name", "ruleName", False),
    ("cost-reduction", "business-line", "businessCategory", False),
    ("cost-reduction", "entity", "legalEntity", True),
    ("cost-reduction", "currency", "creditCurrency", False),
    ("cost-reduction", "market", "creditorMarket", False),
    ("cost-reduction", "obo", "needObo", True),
    ("cost-reduction", "fvt", "needFvt", True),
    ("cost-reduction", "status", "status", False),
    ("retry", "name", "ruleName", False),
    ("retry", "entity", "bizLegalEntityList", True),
    ("retry", "business-line", "businessCategoryList", True),
    ("retry", "bank", "debtorInstList", True),
    ("retry", "currency", "creditorCurrencyList", True),
    ("retry", "region", "creditorCountryList", True),
    ("retry", "bank-account", "debtorAccountNoList", True),
    ("retry", "clearing-network", "clearingNetworkList", True),
    ("retry", "status", "status", False),
    ("retry", "communication-mode", "communicationMode", False),
    ("retry", "integration-mode", "integrationMode", False),
]


def simple_row(slug, identity=1):
    return {
        IDENTITIES[slug]: identity if slug == "same-bank-transfer" else str(identity),
        "future": {"nested": [None, 0, ""]},
    }


def seed(run_cli, setup, slug, rows=None):
    setup.state.business_script.append(page(rows or [simple_row(slug)], slug))
    code, out, _ = refresh(run_cli, slug)
    assert code == 0, out
    return listing(run_cli, slug)[1]


@pytest.mark.parametrize("slug,flag,field,array", FILTER_CASES)
def test_every_flat_filter_exact_matching_and_live_cache_isolation(
    run_cli, envelope, setup, slug, flag, field, array
):
    values = ["MATCH", "match", "*", " MATCH ", "MATCH,OTHER"]
    rows = [
        simple_row(slug, i + 1) | {field: [v, "SECOND"] if array else v}
        for i, v in enumerate(values)
    ]
    rows += [simple_row(slug, 6) | {field: None}, simple_row(slug, 7)]
    old = seed(run_cli, setup, slug, rows)
    for i, value in enumerate(values):
        assert envelope(listing(run_cli, slug, "--" + flag, value)[1])["data"] == [
            rows[i]
        ]
    assert envelope(listing(run_cli, slug, "--" + flag, "ABSENT")[1])["data"] == []
    assert (
        envelope(listing(run_cli, slug, "--" + flag, "MATCH", "--" + flag, "match")[1])[
            "data"
        ]
        == rows[:2]
    )
    for value in ("", "  "):
        assert listing(run_cli, slug, "--" + flag, value)[0] == 2
    before = setup.cache_path.read_bytes()
    setup.state.business_script.append(page(rows, slug))
    code, out, _ = listing(run_cli, slug, "--live", "--" + flag, "MATCH")
    assert code == 0, out
    assert envelope(out)["data"] == [rows[0]]
    assert envelope(out)["meta"]["source"] == "live"
    assert setup.cache_path.read_bytes() == before
    assert listing(run_cli, slug)[1] == old


@pytest.mark.parametrize("slug", SLUGS)
@pytest.mark.parametrize("size", [0, 1, 1000])
def test_single_page_boundaries_and_unfiltered_request(
    run_cli, envelope, setup, slug, size
):
    rows = [simple_row(slug, i) for i in range(size)]
    setup.state.business_script.append(page(rows, slug))
    code, out, _ = refresh(run_cli, slug)
    assert code == 0, out
    assert envelope(out)["data"]["row_count"] == size
    assert setup.state.business_requests == [
        {
            "pageNum" if slug == "same-bank-transfer" else "pageNo": 1
            if slug == "same-bank-transfer"
            else 0,
            "pageSize": 1000,
        }
    ]
    assert len(envelope(listing(run_cli, slug, "--all")[1])["data"]) == size


@pytest.mark.parametrize("slug", SLUGS)
@pytest.mark.parametrize(
    "failure",
    [
        "null",
        "missing",
        "wrong_page",
        "wrong_size",
        "bool_total",
        "negative_total",
        "truncated",
        "overflow",
        "duplicate",
        "identity",
        "bad_pages",
        "refusal",
        "missing_envelope",
        "not_json",
    ],
)
def test_refresh_failure_preserves_snapshot(run_cli, envelope, setup, slug, failure):
    old = seed(run_cli, setup, slug)
    outcome = page([simple_row(slug)], slug)
    data = outcome["body"]["resultObj" if slug == "same-bank-transfer" else "data"]
    rows_key = (
        "payoutBookDecisionRuleVOList"
        if slug == "same-bank-transfer"
        else "businessDataList"
    )
    if failure == "null":
        data[rows_key] = None
    elif failure == "missing":
        del data[rows_key]
    elif failure == "wrong_page":
        data["pageNum" if slug == "same-bank-transfer" else "pageNo"] = 2
    elif failure == "wrong_size":
        data["pageSize"] = 0
    elif failure == "bool_total":
        data["totalCount"] = True
    elif failure == "negative_total":
        data["totalCount"] = -1
    elif failure == "truncated":
        data["totalCount"] = 2
    elif failure == "overflow":
        data["totalCount"] = 1001
    elif failure == "duplicate":
        data[rows_key] *= 2
        data["totalCount"] = 2
    elif failure == "identity":
        data[rows_key] = [
            {IDENTITIES[slug]: True if slug == "same-bank-transfer" else 1}
        ]
    elif failure == "bad_pages":
        data["totalPages" if slug == "same-bank-transfer" else "totalPageNo"] = None
    elif failure == "refusal":
        outcome["body"]["success"] = False
    elif failure == "missing_envelope":
        outcome["body"] = {"success": True}
    elif failure == "not_json":
        outcome["body"] = "PRIVATE-RAW-RESPONSE"
    setup.state.business_script.append(outcome)
    code, out, err = refresh(run_cli, slug)
    assert code == 1, out
    assert envelope(out)["error"]["code"] in {
        "INVALID_RESPONSE",
        "INCOMPLETE_RESULT",
        "BUSINESS_QUERY_FAILED",
    }
    assert "PRIVATE-RAW-RESPONSE" not in out + err
    assert listing(run_cli, slug)[1] == old


@pytest.mark.parametrize("slug", SLUGS)
def test_live_failure_neither_publishes_nor_falls_back(run_cli, envelope, setup, slug):
    for populated in (False, True):
        old = seed(run_cli, setup, slug) if populated else None
        setup.state.business_script.append({"status": 200, "body": {"success": False}})
        code, out, _ = listing(run_cli, slug, "--live")
        assert code == 1
        assert envelope(out)["error"]["code"] == "BUSINESS_QUERY_FAILED"
        if populated:
            assert listing(run_cli, slug)[1] == old
        else:
            assert envelope(listing(run_cli, slug)[1])["error"]["code"] == "CACHE_MISS"


@pytest.mark.parametrize("slug", SLUGS)
def test_display_options_navigation_and_excluded_commands(
    run_cli, envelope, setup, slug
):
    rows = [simple_row(slug, i + 1000) for i in range(150)]
    seed(run_cli, setup, slug, rows)
    setup.state.running = False
    assert len(envelope(listing(run_cli, slug)[1])["data"]) == 100
    assert envelope(listing(run_cli, slug)[1])["meta"]["has_more"] is True
    assert len(envelope(listing(run_cli, slug, "--all")[1])["data"]) == 150
    assert (
        len(
            envelope(listing(run_cli, slug, "--offset", "145", "--limit", "10")[1])[
                "data"
            ]
        )
        == 5
    )
    assert envelope(listing(run_cli, slug, "--offset", "999")[1])["data"] == []
    projected = envelope(
        listing(
            run_cli, slug, "--fields", IDENTITIES[slug] + ",unknown", "--limit", "1"
        )[1]
    )
    assert projected["data"] == [{IDENTITIES[slug]: rows[0][IDENTITIES[slug]]}]
    assert projected["meta"]["complete"] is True
    assert "source: cache" in listing(run_cli, slug, "--format", "table")[1]
    for flags in [
        ("--all", "--limit", "1"),
        ("--all", "--offset", "1"),
        ("--limit", "0"),
        ("--offset", "-1"),
        ("--fields", ""),
        ("--format", "xml"),
    ]:
        assert listing(run_cli, slug, *flags)[0] == 2
    for path in [
        ("payment", "rules", slug),
        ("payment", "rules", slug, "list"),
        ("refresh", "payment", "rules", slug),
        ("describe", "payment", "rules", slug, "list"),
    ]:
        for argv in [
            ["help", *path],
            [*path, "--help"],
            [*path, "-h"],
            ["help", *path, "--format", "text"],
        ]:
            assert run_cli(argv)[0] == 0, argv
    for fmt in ("json", "text"):
        assert (
            run_cli(["describe", "payment", "rules", slug, "list", "--format", fmt])[0]
            == 0
        )
    for verb in ("get", "create", "edit", "delete", "execute", "approve"):
        assert run_cli(["payment", "rules", slug, verb])[0] == 2
    assert run_cli(["refresh", "payment", "rules", slug, "--status", "ON"])[0] == 2
    assert run_cli(["payment", "rules", "flow", "list"])[0] == 2


@pytest.mark.parametrize("slug", SLUGS)
def test_freshness_completeness_and_corruption(run_cli, envelope, setup, slug):
    import sqlite3

    assert envelope(listing(run_cli, slug)[1])["error"]["code"] == "CACHE_MISS"
    seed(run_cli, setup, slug)
    config = setup.tmp_path / "config.toml"
    config.write_text(config.read_text().replace("ttl_hours = 72", "ttl_hours = 0"))
    assert envelope(listing(run_cli, slug)[1])["meta"]["stale"] is True
    assert (
        envelope(listing(run_cli, slug, "--require-fresh")[1])["error"]["code"]
        == "CACHE_STALE"
    )
    with sqlite3.connect(setup.cache_path) as db:
        db.execute("UPDATE snapshots SET backend_complete = 0")
    assert (
        envelope(listing(run_cli, slug, "--require-complete")[1])["error"]["code"]
        == "INCOMPLETE_RESULT"
    )
    with sqlite3.connect(setup.cache_path) as db:
        db.execute("UPDATE snapshots SET row_count = 2")
    code, out, _ = listing(run_cli, slug)
    assert code == 1
    assert "payment.rules." in envelope(out)["error"]["message"]


@pytest.mark.parametrize("slug", SLUGS)
def test_source_isolation_and_snapshot_source_rejection(run_cli, envelope, setup, slug):
    for other in SLUGS:
        seed(run_cli, setup, other, [simple_row(other, 9)])
    assert envelope(listing(run_cli, slug)[1])["data"] == [simple_row(slug, 9)]
    config = setup.tmp_path / "config.toml"
    key = slug.replace("-", "_")
    config.write_text(
        config.read_text().replace(
            f'[sources.payment_rules_{key}]\nkind = "cdp"',
            f'[sources.payment_rules_{key}]\nkind = "snapshot"\n'
            'path = "/synthetic/absent"',
        )
    )
    assert envelope(listing(run_cli, slug)[1])["error"]["code"] == "CONFIG_ERROR"


@pytest.mark.parametrize("slug", SLUGS)
def test_lock_auth_timeout_interrupt_and_publication_failure_keep_old_cache(
    run_cli, envelope, setup, monkeypatch, slug
):
    import sqlite3

    import dogopencli.collect as collect
    from dogopencli.cache import Cache

    old = seed(run_cli, setup, slug)
    with Cache(setup.cache_path).refresh_lock():
        assert envelope(refresh(run_cli, slug)[1])["error"]["code"] == "LOCKED"
    for status, error in [(401, "AUTH_REQUIRED"), (403, "BUSINESS_QUERY_FAILED")]:
        setup.state.business_script.append({"status": status, "body": {}})
        assert envelope(refresh(run_cli, slug)[1])["error"]["code"] == error
        assert listing(run_cli, slug)[1] == old
    setup.state.running = False
    assert (
        envelope(listing(run_cli, slug, "--live")[1])["error"]["code"]
        == "BROWSER_UNAVAILABLE"
    )
    setup.state.running = True

    def interrupt(payload, index):
        raise KeyboardInterrupt

    setup.state.business_handler = interrupt
    assert refresh(run_cli, slug)[0] == 130
    setup.state.business_handler = None
    with monkeypatch.context() as context:
        ticks = iter([0, 901])
        context.setattr(collect, "_monotonic", lambda: next(ticks))
        assert envelope(refresh(run_cli, slug)[1])["error"]["code"] == "TIMEOUT"
    with sqlite3.connect(setup.cache_path) as db:
        db.execute(
            "CREATE TRIGGER reject_publication BEFORE INSERT ON records "
            "BEGIN SELECT RAISE(ABORT, 'SYNTHETIC failure'); END"
        )
    setup.state.business_script.append(page([simple_row(slug, 2)], slug))
    code, out, _ = refresh(run_cli, slug)
    assert code == 1
    assert envelope(out)["error"]["code"] == "CACHE_ERROR"
    assert listing(run_cli, slug)[1] == old


@pytest.mark.parametrize("slug", SLUGS)
def test_exact_request_contract_rejects_mutation_filters_and_pagination(slug):
    from dogopencli.errors import CliError
    from dogopencli.plugins import get_capability
    from dogopencli.transport import QueryRequest, validate_request

    cap = get_capability("payment.rules." + slug.replace("-", "_") + ".list")
    body = (
        {"pageNum": 1, "pageSize": 1000}
        if slug == "same-bank-transfer"
        else {"pageNo": 0, "pageSize": 1000}
    )
    base = dict(
        capability=cap.name,
        method=cap.contract.method,
        host=cap.contract.host,
        path=cap.contract.path,
        body=body,
    )
    for changes in [
        dict(method="DELETE"),
        dict(host="other.example"),
        dict(path=cap.contract.path + "/execute"),
        dict(body=body | {"status": "ON"}),
        dict(body=body | {"ctoken": "SECRET"}),
        dict(body=body | {"pageSize": 20}),
        dict(body=body | {"pageNum" if slug == "same-bank-transfer" else "pageNo": 2}),
        dict(body={}),
    ]:
        with pytest.raises(CliError) as exc:
            validate_request(QueryRequest(**(base | changes)), cap.contract)
        assert exc.value.code == "REQUEST_NOT_ALLOWED"


def test_bank_empty_nodes_and_source_only_filter_remain_visible(
    run_cli, envelope, setup
):
    row = {
        "switchNodeCode": "  SOURCE  ",
        "fundNavigationNodeSwitchRequirementVOList": [],
    }
    seed(run_cli, setup, "bank-switch", [row])
    assert envelope(
        listing(run_cli, "bank-switch", "--source-account", "  SOURCE  ")[1]
    )["data"] == [row]
    assert (
        envelope(listing(run_cli, "bank-switch", "--source-account", "SOURCE")[1])[
            "data"
        ]
        == []
    )
    assert envelope(listing(run_cli, "bank-switch", "--status", "ON")[1])["data"] == []
    for flag in (
        "source-account",
        "source-network",
        "status",
        "target-account",
        "target-network",
    ):
        assert listing(run_cli, "bank-switch", "--" + flag, " ")[0] == 2


def test_bank_nested_type_error_preserves_cache(run_cli, envelope, setup):
    old = seed(run_cli, setup, "bank-switch", [bank_row()])
    row = bank_row()
    row["fundNavigationNodeSwitchRequirementVOList"][0]["switchRuleVOList"] = (
        "PRIVATE-SCHEMA-DRIFT"
    )
    setup.state.business_script.append(page([row], "bank-switch"))
    code, out, err = refresh(run_cli, "bank-switch")
    assert code == 1
    assert envelope(out)["error"]["code"] == "INVALID_RESPONSE"
    assert "PRIVATE-SCHEMA-DRIFT" not in out + err
    assert listing(run_cli, "bank-switch")[1] == old


def test_filters_precede_sort_window_projection(run_cli, envelope, setup):
    rows = [
        {"groupId": "20", "businessCategory": "B", "status": "ON"},
        {"groupId": "001", "businessCategory": "B", "status": "OFF"},
        {"groupId": "10", "businessCategory": "B", "status": "ON"},
    ]
    seed(run_cli, setup, "cost-reduction", rows)
    for live in (False, True):
        if live:
            setup.state.business_script.append(page(rows, "cost-reduction"))
        code, out, _ = listing(
            run_cli,
            "cost-reduction",
            "--business-line",
            "B",
            "--status",
            "ON",
            "--offset",
            "1",
            "--limit",
            "1",
            "--fields",
            "groupId",
            *(["--live"] if live else []),
        )
        assert code == 0, out
        result = envelope(out)
        assert result["data"] == [{"groupId": "20"}]
        assert result["meta"]["matched_total"] == 2
        assert result["meta"]["complete"] is True


@pytest.mark.parametrize("bad", [True, "1", 1.0, None, -1])
def test_same_bank_identity_types_are_strict(run_cli, envelope, setup, bad):
    setup.state.business_script.append(page([{"ruleId": bad}]))
    assert envelope(refresh(run_cli)[1])["error"]["code"] == "INVALID_RESPONSE"


def test_bank_filters_cannot_join_separate_requirements(run_cli, envelope, setup):
    from copy import deepcopy

    row = bank_row()
    first = row["fundNavigationNodeSwitchRequirementVOList"][0]
    second = deepcopy(first)
    first["switchRuleVOList"] = []
    second["switchClearingNetwork"] = "OTHER"
    row["fundNavigationNodeSwitchRequirementVOList"].append(second)
    setup.state.business_script.append(page([row], "bank-switch"))
    assert refresh(run_cli, "bank-switch")[0] == 0
    for flag, value in (
        ("--status", "ON"),
        ("--target-account", "TARGET"),
        ("--target-network", "WIRE"),
    ):
        result = listing(run_cli, "bank-switch", "--source-network", "NET", flag, value)
        assert result[0] == 0
        assert envelope(result[1])["data"] == []
    assert (
        envelope(listing(run_cli, "bank-switch", "--source-network", "NET")[1])["data"]
        == []
    )


@pytest.mark.parametrize(
    "flag,value",
    [
        ("--source-account", "SOURCE"),
        ("--source-network", "NET"),
        ("--status", "ON"),
        ("--target-account", "TARGET"),
        ("--target-network", "WIRE"),
    ],
)
def test_bank_filter_exact_values_and_repeated_or(
    run_cli, envelope, setup, flag, value
):
    row = bank_row()
    setup.state.business_script.append(page([row], "bank-switch"))
    assert refresh(run_cli, "bank-switch")[0] == 0
    for mismatch in (value.lower(), "*", " " + value, value + ",OTHER"):
        result = listing(run_cli, "bank-switch", flag, mismatch)
        assert result[0] == 0
        assert envelope(result[1])["data"] == []
    result = listing(run_cli, "bank-switch", flag, "MISSING", flag, value)
    assert result[0] == 0
    assert envelope(result[1])["data"] == [row]
