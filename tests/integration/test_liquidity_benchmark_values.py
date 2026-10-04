"""Daily market benchmarks through the public CLI, fake CDP and real SQLite."""

import pytest

from dogopencli.jsonutil import parse

pytest_plugins = ["test_liquidity_cli_sit"]

FIELDS = (
    "id",
    "effectiveDate",
    "strategyBenchmarkType",
    "currency",
    "colorType",
    "value",
)
OPTIONS = ["--from-date", "20261001", "--to-date", "20261004"]


def benchmark(index=0, **overrides):
    return {
        "id": "",
        "effectiveDate": "20261002",
        "strategyBenchmarkType": (
            "passiveInterestBenchmark" if index < 9 else "tenorStrategyBenchmark"
        ),
        "currency": ("USD", "EUR", "HKD")[index % 3],
        "colorType": ("RED", "YELLOW", "GREEN")[(index // 3) % 3],
        "value": "2.0012300",
        **overrides,
    }


def command(*extra, refresh=False, options=None):
    return (
        (
            ["refresh", "liquidity", "investment", "benchmark-values"]
            if refresh
            else ["liquidity", "investment", "benchmark-values", "list"]
        )
        + (OPTIONS if options is None else options)
        + list(extra)
    )


def page(rows, total):
    return {
        "status": 200,
        "body": {"success": True, "data": {"data": rows, "totalCount": total}},
    }


def listing(rows):
    def answer(body, index):
        return page(rows[body["rowStart"] : body["rowStart"] + 10], len(rows))

    return answer


def ordered(rows):
    return sorted(rows, key=lambda row: tuple(row[field] for field in FIELDS[1:5]))


def test_composite_identity_wire_precision_privacy_and_offline_live_isolation(
    setup, run_cli
):
    rows = [benchmark(index) for index in range(12)]
    for index, value in enumerate((None, "", "0")):
        rows[index]["value"] = value
    raw = [dict(row, privateMemo="SYNTHETIC PRIVATE") for row in rows]

    def answer(body, index):
        assert body == {
            "tntInstId": "GUAPW3SG",
            "timeZone": "GMT+08",
            "valueDateStart": "20261001",
            "valueDateEnd": "20261004",
            "rowStart": body["rowStart"],
            "pageSize": 10,
        }
        return listing(raw)(body, index)

    setup.state.business_handler = answer
    code, out, err = run_cli(command("--require-complete", refresh=True))
    assert code == 0, err
    refreshed = parse(out)
    assert refreshed["data"]["row_count"] == 12
    assert refreshed["meta"]["complete"] is True
    assert [body["rowStart"] for body in setup.state.business_requests] == [0, 10]
    before = setup.cache_path.read_bytes()
    code, out, err = run_cli(command("--live", "--all", "--require-complete"))
    assert code == 0, err
    assert ordered(parse(out)["data"]) == ordered(rows)
    assert setup.cache_path.read_bytes() == before
    count = len(setup.state.business_requests)
    setup.state.reachable = False
    code, out, err = run_cli(command("--all", "--require-complete"))
    assert code == 0, err
    cached = parse(out)
    assert ordered(cached["data"]) == ordered(rows)
    assert cached["meta"]["fetched_at"] == refreshed["meta"]["fetched_at"]
    assert len(setup.state.business_requests) == count
    assert b"SYNTHETIC PRIVATE" not in setup.cache_path.read_bytes()


def test_later_refresh_revises_same_identity_and_offline_subwindow_uses_business_day(
    setup, run_cli
):
    setup.state.business_handler = listing([benchmark()])
    code, _, err = run_cli(command(refresh=True))
    assert code == 0, err
    revised = benchmark(value="3.00000")
    setup.state.business_handler = listing([revised])
    code, _, err = run_cli(command(refresh=True))
    assert code == 0, err
    setup.state.reachable = False
    code, out, err = run_cli(
        command(
            "--all",
            "--require-complete",
            options=["--from-date", "20261002", "--to-date", "20261002"],
        )
    )
    assert code == 0, err
    assert parse(out)["data"] == [revised]
    code, out, err = run_cli(
        command(
            "--all",
            "--require-complete",
            options=["--from-date", "20261003", "--to-date", "20261003"],
        )
    )
    assert code == 0, err
    assert parse(out)["data"] == []
    assert parse(out)["meta"]["complete"] is True


def test_empty_capture_and_empty_live_preserve_cache(setup, run_cli):
    setup.state.business_handler = listing([])
    code, out, err = run_cli(command("--live", "--all", "--require-complete"))
    assert code == 0, err
    assert parse(out)["data"] == []
    assert not setup.cache_path.exists()
    code, out, err = run_cli(command("--require-complete", refresh=True))
    assert code == 0, err
    assert parse(out)["meta"]["published"] is True
    before = setup.cache_path.read_bytes()
    code, _, err = run_cli(command("--live", "--all"))
    assert code == 0, err
    assert setup.cache_path.read_bytes() == before
    setup.state.reachable = False
    code, out, err = run_cli(command("--all", "--require-complete"))
    assert code == 0, err
    assert parse(out)["data"] == []
    assert parse(out)["meta"]["complete"] is True


@pytest.mark.parametrize(
    "options",
    [
        [],
        ["--from-date", "20261001"],
        ["--from-date", "20261005", "--to-date", "20261004"],
        ["--from-date", "20260230", "--to-date", "20261004"],
        [*OPTIONS, "--time-zone", "GMT+00"],
    ],
)
def test_invalid_scope_refused_before_contact(setup, run_cli, options):
    for refresh in (False, True):
        code, _, _ = run_cli(
            command(*([] if refresh else ["--live"]), refresh=refresh, options=options)
        )
        assert code == 2
    assert not setup.state.business_requests
    assert not setup.cache_path.exists()


@pytest.mark.parametrize(
    "defect",
    [
        "conflict",
        "total-drift",
        "auth",
        "business-envelope",
        "wrong-tenant",
        "bad-day",
        "outside-day",
        "missing-dimension",
        "bool-dimension",
        "numeric-dimension",
        "bad-number",
        "numeric-value",
    ],
)
def test_hard_failure_preserves_prior_cache(setup, run_cli, defect):
    setup.state.business_handler = listing([benchmark()])
    code, _, err = run_cli(command(refresh=True))
    assert code == 0, err
    before = setup.cache_path.read_bytes()

    def fail(body, index):
        if defect == "auth":
            return {"status": 401, "body": {"success": False}}
        if defect == "business-envelope":
            return {"status": 200, "body": {"success": False}}
        overrides = {
            "wrong-tenant": {"tntInstId": "OTHER"},
            "bad-day": {"effectiveDate": "20260230"},
            "outside-day": {"effectiveDate": "20261005"},
            "missing-dimension": {"colorType": ""},
            "bool-dimension": {"currency": True},
            "numeric-dimension": {"strategyBenchmarkType": 1},
            "bad-number": {"value": "NaN"},
            "numeric-value": {"value": 0.65},
        }
        if defect in overrides:
            return page([benchmark(**overrides[defect])], 1)
        if body["rowStart"] == 0:
            return page([benchmark(i) for i in range(10)], 12)
        if defect == "conflict":
            return page([benchmark(value="999"), benchmark(10)], 12)
        return page([benchmark(10), benchmark(11)], 13)

    setup.state.business_handler = fail
    for refresh in (False, True):
        code, out, _ = run_cli(
            command(*([] if refresh else ["--live", "--all"]), refresh=refresh)
        )
        assert code == 1
        assert parse(out)["data"] is None
        expected_error = {
            "auth": "AUTH_REQUIRED",
            "business-envelope": "BUSINESS_QUERY_FAILED",
        }.get(defect, "INVALID_RESPONSE")
        assert parse(out)["error"]["code"] == expected_error
        assert setup.cache_path.read_bytes() == before


def test_overlap_partial_policy_and_strict_no_publication(setup, run_cli):
    setup.state.business_handler = listing([benchmark()])
    code, _, err = run_cli(command(refresh=True))
    assert code == 0, err
    before = setup.cache_path.read_bytes()

    def overlap(body, index):
        return (
            page([benchmark(i) for i in range(10)], 12)
            if body["rowStart"] == 0
            else page([benchmark(9), benchmark(10)], 12)
        )

    setup.state.business_handler = overlap
    code, out, _ = run_cli(command("--require-complete", refresh=True))
    assert code == 1
    assert parse(out)["error"]["code"] == "INCOMPLETE_RESULT"
    assert setup.cache_path.read_bytes() == before
    code, out, err = run_cli(command(refresh=True))
    assert code == 0, err
    assert parse(out)["meta"]["complete"] is False
    assert parse(out)["meta"]["published"] is True
    setup.state.reachable = False
    code, out, err = run_cli(command("--all"))
    assert code == 0, err
    assert len(parse(out)["data"]) == 11
    assert parse(out)["meta"]["complete"] is False
    assert "INCOMPLETE_RESULT" in err
    code, out, _ = run_cli(command("--all", "--require-complete"))
    assert code == 1
    assert parse(out)["data"] is None


def test_offline_help_describe_documents_business_identity_and_percent(setup, run_cli):
    setup.state.reachable = False
    code, out, err = run_cli(
        ["help", "liquidity", "investment", "benchmark-values", "list"]
    )
    assert code == 0, err
    assert "daily market interest benchmarks" in parse(out)["summary"]
    code, out, err = run_cli(
        ["describe", "liquidity", "investment", "benchmark-values", "list"]
    )
    assert code == 0, err
    document = parse(out)
    guide = document["read_guide"]
    assert guide["identity"] == [
        "effectiveDate",
        "strategyBenchmarkType",
        "currency",
        "colorType",
    ]
    assert guide["offline_profile"] == "dated"
    assert guide["series_time"] == "effectiveDate"
    assert guide["live_verified"] == "2026-10-04"
    properties = document["data_schema"]["properties"]
    assert set(properties) == set(FIELDS)
    assert properties["value"]["x-unit"] == "percent"
    assert properties["effectiveDate"]["x-format"] == "YYYYMMDD"
    assert (
        properties["colorType"]["x-evidence"]["meaning"]
        == "operator confirmed 2026-10-04"
    )
    assert not setup.state.business_requests
