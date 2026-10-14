"""Unified account inquiry through public CLI, fake CDP and temporary SQLite."""

import json

import pytest

from dogopencli.jsonutil import parse

pytest_plugins = ["test_liquidity_cli_sit"]


def account(alias="A", **fields):
    return {
        "aliasName": alias,
        "currency": "USD",
        "bankId": "B",
        "instId": "E",
        **fields,
    }


def native_handler(cash, baselines, details=None):
    details = details or {row["aliasName"]: row for row in baselines}

    def answer(payload, index):
        if "bankAccountQueryVO" in payload:
            request = json.loads(payload["bankAccountQueryVO"])
            rows, container = cash, "bankAccountPropertyVOList"
        elif "bankAccountBaseLineQuery" in payload:
            request = json.loads(payload["bankAccountBaseLineQuery"])
            rows, container = baselines, "data"
        else:
            detail = details[payload["aliasName"]]
            if detail is False:
                return {
                    "status": 200,
                    "body": {
                        "resultFlag": True,
                        "errorCode": "ACCOUNT_REFUSED",
                        "errorMessage": "secret",
                        "result": {"success": False},
                    },
                }
            return {
                "status": 200,
                "body": {"resultFlag": True, "result": {"data": detail}},
            }
        start, size = request["rowStart"], request["pageSize"]
        return {
            "status": 200,
            "body": {
                "resultFlag": True,
                "count": len(rows),
                "result": {container: rows[start : start + size]},
            },
        }

    return answer


def test_live_merges_sources_with_baseline_classification_and_detail(setup, run_cli):
    setup.state.business_handler = native_handler(
        [
            account(
                id="SHARED",
                accountType="CA",
                status="Norm",
                accountNo="001",
                gmtModified="cash",
                rate="0.0000",
            )
        ],
        [account(accountType="OA", status="NORMAL", timeZone="GMT+08")],
        {
            "A": account(
                accountType="OA",
                status="NORMAL",
                gmtModified="detail",
                h2hNetWorkVOList=[{"limit": "0.00"}],
            )
        },
    )
    code, out, err = run_cli(
        ["liquidity", "cash", "accounts", "list", "--live", "--require-complete"]
    )
    assert code == 0, err
    result = parse(out)
    row = result["data"][0]
    assert (row["accountType"], row["status"]) == ("OA", "NORMAL")
    assert row["rate"] == "0.0000"
    assert row["gmtModified"] == "cash"
    assert row["h2hNetWorkVOList"] == [{"limit": "0.00"}]
    assert row["detail_state"] == "succeeded"
    assert row["source_metadata"]["raw"]["detail"]["gmtModified"] == "detail"
    assert result["meta"]["detail_coverage"]["succeeded"] == 1
    assert (
        json.loads(setup.state.business_requests[1]["bankAccountBaseLineQuery"])[
            "pageSize"
        ]
        == 1000
    )
    assert not setup.cache_path.exists()


def test_refused_detail_retains_rows_strict_rejects_and_cache_replays(setup, run_cli):
    setup.state.business_handler = native_handler(
        [account(accountType="SVF", status="Norm")],
        [account(accountType="", status="OTHER", supportBlockchain=False)],
        {"A": False},
    )
    code, out, err = run_cli(["refresh", "liquidity", "cash", "accounts"])
    assert code == 0, err
    result = parse(out)
    assert result["meta"]["list_coverage"]["complete"] is True
    assert result["meta"]["detail_coverage"]["refused"] == 1
    before = setup.cache_path.read_bytes()
    setup.state.business_requests.clear()
    code, out, err = run_cli(["liquidity", "cash", "accounts", "list"])
    assert code == 0, err
    row = parse(out)["data"][0]
    assert row["accountType"] == ""
    assert row["status"] == "OTHER"
    assert row["detail_state"] == "refused"
    assert row["source_metadata"]["detail_error"] == {
        "code": "BUSINESS_QUERY_FAILED",
        "native_code": "ACCOUNT_REFUSED",
        "message": "backend refused account detail",
    }
    assert "secret" not in out
    assert setup.state.business_requests == []
    code, out, err = run_cli(
        ["liquidity", "cash", "accounts", "list", "--require-complete"]
    )
    assert code == 1
    assert parse(out)["data"] is None
    assert "DETAIL_COVERAGE_INCOMPLETE" in parse(out)["error"]["message"]
    assert setup.cache_path.read_bytes() == before


@pytest.mark.parametrize("identity", ["aliasName", "currency", "bankId", "instId"])
def test_detail_wrong_identity_is_hard_failure_and_preserves_cache(
    setup, run_cli, identity
):
    setup.state.business_handler = native_handler([account()], [account()])
    assert run_cli(["refresh", "liquidity", "cash", "accounts"])[0] == 0
    before = setup.cache_path.read_bytes()
    setup.state.business_handler = native_handler(
        [account()], [account()], {"A": account(**{identity: "WRONG"})}
    )
    code, out, err = run_cli(["refresh", "liquidity", "cash", "accounts"])
    assert code == 1
    assert parse(out)["error"]["code"] == "INVALID_RESPONSE"
    assert setup.cache_path.read_bytes() == before


def test_unmatched_accounts_retained_and_shared_cash_id_never_joins(setup, run_cli):
    setup.state.business_handler = native_handler(
        [
            account("A", id="shared", accountType="CA", status="Norm"),
            account("C", id="shared"),
        ],
        [
            account("A", accountType="OA", status="NORMAL"),
            account("B", accountType="FLC", status="NORMAL"),
        ],
    )
    code, out, err = run_cli(
        ["liquidity", "cash", "accounts", "list", "--live", "--limit", "0"]
    )
    assert code == 0, err
    result = parse(out)
    assert [row["aliasName"] for row in result["data"]] == ["A", "C", "B"]
    assert "accountType" not in result["data"][1]
    assert result["meta"]["complete"] is False
    assert result["meta"]["list_coverage"] == {
        "complete": False,
        "matched": 1,
        "cash_only": 1,
        "baseline_only": 1,
    }


def test_detail_nonidentity_conflict_keeps_baseline_and_source_evidence(setup, run_cli):
    setup.state.business_handler = native_handler(
        [account()],
        [account(timeZone="GMT+08")],
        {"A": account(timeZone="UTC", unknownNested={"value": None})},
    )
    code, out, err = run_cli(["liquidity", "cash", "accounts", "list", "--live"])
    assert code == 0, err
    row = parse(out)["data"][0]
    assert row["timeZone"] == "GMT+08"
    assert row["unknownNested"] == {"value": None}
    assert row["source_metadata"]["conflicts"]["timeZone"] == {
        "baseline": "GMT+08",
        "detail": "UTC",
    }


def test_cash_only_prior_slot_requires_refresh_without_network_or_writes(
    setup, run_cli
):
    from dogopencli.cache import Cache
    from dogopencli.result_policy import AcquisitionEvidence
    from dogopencli.temporary_query import publish_slot

    store = Cache(setup.cache_path)
    with store.refresh_lock():
        publish_slot(
            store,
            "liquidity.cash.accounts",
            [account()],
            capability="liquidity.cash.accounts.list",
            scope={},
            variant="/queryintnalbkactlist.json",
            fetched_at="2026-10-13T00:00:00+00:00",
            evidence=AcquisitionEvidence.for_collection(
                complete=True, reported_total=1, collected_total=1
            ),
        )
    before = setup.cache_path.read_bytes()
    code, out, err = run_cli(["liquidity", "cash", "accounts", "list"])
    assert code == 1
    assert parse(out)["error"]["code"] == "INVALID_RESPONSE"
    assert "refresh liquidity cash accounts" in parse(out)["error"]["message"]
    assert setup.state.business_requests == []
    assert setup.cache_path.read_bytes() == before


def hole_handler(hole=3, refused=False):
    native = [
        account(f"A{i}", accountType="CA", status="Norm") if i != hole else None
        for i in range(8)
    ]
    baselines = [
        account(row["aliasName"], accountType="OA", status="NORMAL")
        for row in native
        if row
    ]
    normal = native_handler(
        [row for row in native if row],
        baselines,
        {
            row["aliasName"]: False if refused and row["aliasName"] == "A0" else row
            for row in baselines
        },
    )

    def answer(payload, index):
        if "bankAccountQueryVO" not in payload:
            return normal(payload, index)
        request = json.loads(payload["bankAccountQueryVO"])
        start, size = request["rowStart"], request["pageSize"]
        rows = [row for row in native[start : start + size] if row]
        return {
            "status": 200,
            "body": {
                "resultFlag": True,
                "count": 8,
                "result": {"bankAccountPropertyVOList": rows},
            },
        }

    return answer


def test_verified_moved_hole_strict_refresh_offline_replay_and_live_isolation(
    setup, run_cli
):
    setup.state.business_handler = hole_handler()
    code, out, err = run_cli(
        ["refresh", "liquidity", "cash", "accounts", "--require-complete"]
    )
    assert code == 0, err
    meta = parse(out)["meta"]
    assert meta["complete"] is True
    assert meta["sources"]["cash"]["reported_total"] == 8
    assert meta["sources"]["cash"]["collected_total"] == 7
    assert meta["accepted_diagnostics"][0]["effective_total"] == 7
    assert meta["accepted_diagnostics"][0]["hole_offset"] == 3
    assert meta["acquisition"]["reasons"] == []
    hint = setup.tmp_path / "cache.sqlite3.account-hole-hints.json"
    assert hint.exists()
    before, hint_before = setup.cache_path.read_bytes(), hint.read_bytes()
    setup.state.business_requests.clear()
    code, out, err = run_cli(
        [
            "liquidity",
            "cash",
            "accounts",
            "list",
            "--require-complete",
            "--status",
            "NORMAL",
            "--limit",
            "1",
            "--fields",
            "aliasName,status",
        ]
    )
    assert code == 0, err
    assert parse(out)["data"] == [{"aliasName": "A0", "status": "NORMAL"}]
    assert parse(out)["meta"]["detail_coverage"]["succeeded"] == 7
    assert setup.state.business_requests == []
    assert hint.read_bytes() == hint_before
    setup.state.business_handler = hole_handler(hole=4)
    code, out, err = run_cli(
        ["liquidity", "cash", "accounts", "list", "--live", "--require-complete"]
    )
    assert code == 0, err
    assert parse(out)["meta"]["accepted_diagnostics"][0]["hole_offset"] == 4
    assert setup.cache_path.read_bytes() == before


def test_verified_hole_with_detail_refusal_strict_reason_and_hint_persistence(
    setup, run_cli
):
    setup.state.business_handler = hole_handler(refused=True)
    code, out, err = run_cli(
        ["liquidity", "cash", "accounts", "list", "--live", "--require-complete"]
    )
    assert code == 1
    result = parse(out)
    assert result["data"] is None
    assert "DETAIL_COVERAGE_INCOMPLETE" in result["error"]["message"]
    assert "COUNT_SHORTFALL" not in result["error"]["message"]
    assert result["meta"]["list_coverage"]["complete"] is True
    assert result["meta"]["detail_coverage"]["refused"] == 1
    assert (setup.tmp_path / "cache.sqlite3.account-hole-hints.json").exists()
    assert not setup.cache_path.exists()


def test_baseline_full_pagination_with_display_limit_and_one_detail_each(
    setup, run_cli
):
    cash = [account(f"A{i}", id="shared") for i in range(1001)]
    baselines = [account(f"A{i}", status="NORMAL") for i in range(1001)]
    setup.state.business_handler = native_handler(cash, baselines)
    code, out, err = run_cli(
        ["liquidity", "cash", "accounts", "list", "--live", "--limit", "1"]
    )
    assert code == 0, err
    result = parse(out)
    assert len(result["data"]) == 1
    assert result["meta"]["detail_coverage"]["attempted"] == 1001
    pages = [
        json.loads(payload["bankAccountBaseLineQuery"])
        for payload in setup.state.business_requests
        if "bankAccountBaseLineQuery" in payload
    ]
    assert [(page["rowStart"], page["pageSize"]) for page in pages] == [
        (0, 1000),
        (1000, 1000),
    ]
    assert (
        len(
            [
                payload
                for payload in setup.state.business_requests
                if "aliasName" in payload
            ]
        )
        == 1001
    )


@pytest.mark.parametrize("failure", ["empty", "strict_refusal", "malformed", "auth"])
def test_failed_or_empty_refresh_preserves_prior_composite_slot(
    setup, run_cli, failure
):
    setup.state.business_handler = native_handler([account()], [account()])
    assert run_cli(["refresh", "liquidity", "cash", "accounts"])[0] == 0
    before = setup.cache_path.read_bytes()
    if failure == "empty":
        setup.state.business_handler = native_handler([], [])
    elif failure == "strict_refusal":
        setup.state.business_handler = native_handler(
            [account()], [account()], {"A": False}
        )
    else:
        normal = native_handler([account()], [account()])

        def answer(payload, index):
            if "aliasName" in payload:
                if failure == "auth":
                    return {"status": 401, "body": {}}
                return {
                    "status": 200,
                    "body": {"resultFlag": True, "result": {"data": []}},
                }
            return normal(payload, index)

        setup.state.business_handler = answer
    code, out, err = run_cli(
        ["refresh", "liquidity", "cash", "accounts", "--require-complete"]
    )
    result = parse(out)
    if failure == "empty":
        assert code == 0, err
        assert result["meta"]["published"] is False
    else:
        assert code == 1
        assert (
            result["error"]["code"]
            == {
                "strict_refusal": "INCOMPLETE_RESULT",
                "malformed": "INVALID_RESPONSE",
                "auth": "AUTH_REQUIRED",
            }[failure]
        )
    assert setup.cache_path.read_bytes() == before


@pytest.mark.parametrize("empty_first", [False, True])
def test_cash_anomalous_page_keeps_later_native_range(setup, run_cli, empty_first):
    cash = [account("TAIL")]
    baseline = [account("TAIL")]
    normal = native_handler(cash, baseline)

    def answer(payload, index):
        if "bankAccountQueryVO" not in payload:
            return normal(payload, index)
        request = json.loads(payload["bankAccountQueryVO"])
        start = request["rowStart"]
        if request["pageSize"] != 5000:
            return {
                "status": 200,
                "body": {
                    "resultFlag": True,
                    "count": 5001,
                    "result": {"bankAccountPropertyVOList": []},
                },
            }
        rows = (
            []
            if start == 0 and empty_first
            else [account("FIRST")]
            if start == 0
            else cash
        )
        return {
            "status": 200,
            "body": {
                "resultFlag": True,
                "count": 5001,
                "result": {"bankAccountPropertyVOList": rows},
            },
        }

    setup.state.business_handler = answer
    code, out, err = run_cli(
        ["liquidity", "cash", "accounts", "list", "--live", "--limit", "0"]
    )
    assert code == 0, err
    result = parse(out)
    assert "TAIL" in [row["aliasName"] for row in result["data"]]
    assert result["meta"]["complete"] is False
    assert result["meta"]["sources"]["cash"]["reported_total"] == 5001
    pages = [
        json.loads(payload["bankAccountQueryVO"])["rowStart"]
        for payload in setup.state.business_requests
        if "bankAccountQueryVO" in payload
    ]
    assert pages == [0, 5000]


def test_successful_native_null_detail_is_hard_and_preserves_prior_cache(
    setup, run_cli
):
    normal = native_handler([account()], [account()])
    setup.state.business_handler = normal
    assert run_cli(["refresh", "liquidity", "cash", "accounts"])[0] == 0
    before = setup.cache_path.read_bytes()

    def answer(payload, index):
        if "aliasName" in payload:
            return {
                "status": 200,
                "body": {
                    "resultFlag": True,
                    "count": 0,
                    "result": {
                        "success": True,
                        "data": None,
                        "count": 0,
                        "detailMessage": None,
                        "errorCode": None,
                        "errorContext": None,
                        "errorMessage": None,
                    },
                },
            }
        return normal(payload, index)

    setup.state.business_handler = answer
    code, out, err = run_cli(["refresh", "liquidity", "cash", "accounts"])
    assert code == 1
    result = parse(out)
    assert result["error"]["code"] == "INVALID_RESPONSE"
    assert result["error"]["message"] == "detail payload is not an object"
    assert result["data"] is None
    assert setup.cache_path.read_bytes() == before


def test_cash_currency_identities_join_only_matching_baseline_and_replay(
    setup, run_cli
):
    setup.state.business_handler = native_handler(
        [account(id="shared"), account(id="shared", currency="EUR")],
        [account(accountType="OA", status="NORMAL")],
    )
    code, out, err = run_cli(["refresh", "liquidity", "cash", "accounts"])
    assert code == 0, err
    assert parse(out)["meta"]["list_coverage"] == {
        "complete": False,
        "matched": 1,
        "cash_only": 1,
        "baseline_only": 0,
    }
    assert sum("aliasName" in p for p in setup.state.business_requests) == 1
    setup.state.business_requests.clear()
    code, out, err = run_cli(["liquidity", "cash", "accounts", "list"])
    assert code == 0, err
    rows = parse(out)["data"]
    assert [(row["aliasName"], row["currency"]) for row in rows] == [
        ("A", "USD"),
        ("A", "EUR"),
    ]
    assert rows[0]["detail_state"] == "succeeded"
    assert rows[1]["detail_state"] == "missing"
    assert "accountType" not in rows[1]
    assert setup.state.business_requests == []


def test_unmatched_cash_account_keeps_optional_empty_bank_entity(setup, run_cli):
    setup.state.business_handler = native_handler(
        [{"aliasName": "A", "currency": "USD", "bankId": None, "instId": ""}], []
    )
    code, out, err = run_cli(["liquidity", "cash", "accounts", "list", "--live"])
    assert code == 0, err
    result = parse(out)
    assert result["meta"]["complete"] is False
    assert result["data"][0]["bankId"] is None
    assert result["data"][0]["instId"] == ""
    assert result["data"][0]["source_metadata"]["matched"] is False


def test_equal_common_fields_keep_baseline_provenance_on_cache_replay(setup, run_cli):
    setup.state.business_handler = native_handler(
        [account(timeZone="UTC")], [account(timeZone="UTC")]
    )
    assert run_cli(["refresh", "liquidity", "cash", "accounts"])[0] == 0
    setup.state.business_requests.clear()
    code, out, err = run_cli(["liquidity", "cash", "accounts", "list"])
    assert code == 0, err
    row = parse(out)["data"][0]
    assert row["source_metadata"]["provenance"]["timeZone"] == "baseline"
    assert row["source_metadata"]["provenance"]["aliasName"] == "baseline"
    assert "timeZone" not in row["source_metadata"]["conflicts"]
    assert setup.state.business_requests == []


@pytest.mark.parametrize("failure", ["json", "permission"])
def test_invalid_detail_or_outer_request_failure_preserves_cache(
    setup, run_cli, failure
):
    normal = native_handler([account()], [account()])
    setup.state.business_handler = normal
    assert run_cli(["refresh", "liquidity", "cash", "accounts"])[0] == 0
    before = setup.cache_path.read_bytes()

    def answer(payload, index):
        if "aliasName" not in payload:
            return normal(payload, index)
        body = (
            "invalid JSON"
            if failure == "json"
            else {
                "resultFlag": False,
                "result": {"success": False, "errorCode": "PERMISSION_DENIED"},
            }
        )
        return {"status": 200, "body": body}

    setup.state.business_handler = answer
    code, out, err = run_cli(["refresh", "liquidity", "cash", "accounts"])
    result = parse(out)
    assert code == 1
    assert result["error"]["code"] == (
        "INVALID_RESPONSE" if failure == "json" else "BUSINESS_QUERY_FAILED"
    )
    assert result["data"] is None
    assert result["meta"]["published"] is False
    assert setup.cache_path.read_bytes() == before


def test_hole_probe_cancellation_preserves_cache_and_does_not_save_hint(setup, run_cli):
    setup.state.business_handler = native_handler([account()], [account()])
    assert run_cli(["refresh", "liquidity", "cash", "accounts"])[0] == 0
    before = setup.cache_path.read_bytes()
    normal = hole_handler()

    def interrupted(payload, index):
        if "bankAccountQueryVO" in payload:
            request = json.loads(payload["bankAccountQueryVO"])
            if request["pageSize"] == 1:
                raise KeyboardInterrupt
        return normal(payload, index)

    setup.state.business_handler = interrupted
    code, out, err = run_cli(["refresh", "liquidity", "cash", "accounts"])
    assert code == 130
    assert "interrupted" in err
    assert setup.cache_path.read_bytes() == before
    assert not (setup.tmp_path / "cache.sqlite3.account-hole-hints.json").exists()


def test_cash_rediscovery_stays_within_the_short_native_page(setup, run_cli):
    native = [account(f"A{i}") if i != 5000 else None for i in range(5002)]
    normal = native_handler([], [])

    def answer(payload, index):
        if "bankAccountQueryVO" not in payload:
            return normal(payload, index)
        request = json.loads(payload["bankAccountQueryVO"])
        start, size = request["rowStart"], request["pageSize"]
        return {
            "status": 200,
            "body": {
                "resultFlag": True,
                "count": 5002,
                "result": {
                    "bankAccountPropertyVOList": [
                        row for row in native[start : start + size] if row is not None
                    ]
                },
            },
        }

    setup.state.business_handler = answer
    code, out, err = run_cli(["liquidity", "cash", "accounts", "list", "--live"])
    assert code == 0, err
    result = parse(out)
    assert result["meta"]["accepted_diagnostics"][0]["hole_offset"] == 5000
    assert result["meta"]["complete"] is False  # No baseline coverage.
    cash_requests = [
        json.loads(p["bankAccountQueryVO"])
        for p in setup.state.business_requests
        if "bankAccountQueryVO" in p
    ]
    assert [(p["rowStart"], p["pageSize"]) for p in cash_requests[:2]] == [
        (0, 5000),
        (5000, 5000),
    ]
    assert all(p["pageSize"] <= 3 for p in cash_requests[2:])


def test_ambiguous_baseline_alias_is_still_hard_failure(setup, run_cli):
    setup.state.business_handler = native_handler(
        [account(), account(currency="EUR")],
        [account(), account(currency="EUR")],
    )
    code, out, err = run_cli(["liquidity", "cash", "accounts", "list", "--live"])
    assert code == 1
    assert parse(out)["error"]["code"] == "INVALID_RESPONSE"
    assert not any("aliasName" in p for p in setup.state.business_requests)


@pytest.mark.parametrize("field", ["bankId", "instId"])
def test_malformed_detail_qualifier_is_not_hidden_by_missing_list_value(
    setup, run_cli, field
):
    normal = native_handler([account(**{field: None})], [account(**{field: None})])
    setup.state.business_handler = normal
    assert run_cli(["refresh", "liquidity", "cash", "accounts"])[0] == 0
    before = setup.cache_path.read_bytes()
    setup.state.business_handler = native_handler(
        [account(**{field: None})],
        [account(**{field: None})],
        {"A": account(**{field: 0})},
    )
    code, out, err = run_cli(["refresh", "liquidity", "cash", "accounts"])
    assert code == 1
    assert parse(out)["error"]["code"] == "INVALID_RESPONSE"
    assert setup.cache_path.read_bytes() == before


@pytest.mark.parametrize("field", ["bankId", "instId"])
def test_missing_baseline_qualifier_cannot_hide_cash_detail_conflict(
    setup, run_cli, field
):
    setup.state.business_handler = native_handler([account()], [account()])
    assert run_cli(["refresh", "liquidity", "cash", "accounts"])[0] == 0
    before = setup.cache_path.read_bytes()
    setup.state.business_handler = native_handler(
        [account()],
        [account(**{field: None})],
        {"A": account(**{field: "CONFLICT"})},
    )
    code, out, err = run_cli(["refresh", "liquidity", "cash", "accounts"])
    assert code == 1
    assert parse(out)["error"]["code"] == "INVALID_RESPONSE"
    assert parse(out)["meta"]["published"] is False
    assert setup.cache_path.read_bytes() == before


@pytest.mark.parametrize("field", ["bankId", "instId"])
def test_cached_missing_baseline_qualifier_cannot_hide_cash_detail_conflict(
    setup, run_cli, field
):
    from dogopencli.cache import Cache
    from dogopencli.result_policy import AcquisitionEvidence
    from dogopencli.temporary_query import publish_slot

    setup.state.business_handler = native_handler(
        [account()],
        [account(**{field: None})],
        {"A": account()},
    )
    assert run_cli(["refresh", "liquidity", "cash", "accounts"])[0] == 0
    code, out, err = run_cli(["liquidity", "cash", "accounts", "list"])
    assert code == 0, err
    result = parse(out)
    # Reproduce an old falsely complete slot without changing its canonical
    # baseline-owned null field or its otherwise consistent source metadata.
    row = result["data"][0]
    row["source_metadata"]["raw"]["detail"][field] = "CONFLICT"
    row["source_metadata"]["conflicts"][field]["detail"] = "CONFLICT"
    store = Cache(setup.cache_path)
    with store.refresh_lock():
        publish_slot(
            store,
            "liquidity.cash.accounts",
            [row],
            capability="liquidity.cash.accounts.list",
            scope={},
            variant="/queryintnalbkactlist.json",
            fetched_at=result["meta"]["fetched_at"],
            evidence=AcquisitionEvidence.from_record(result["meta"]["acquisition"]),
        )
    before = setup.cache_path.read_bytes()
    setup.state.business_requests.clear()
    code, out, err = run_cli(
        ["liquidity", "cash", "accounts", "list", "--require-complete"]
    )
    assert code == 1
    assert parse(out)["error"]["code"] == "INVALID_RESPONSE"
    assert setup.state.business_requests == []
    assert setup.cache_path.read_bytes() == before
