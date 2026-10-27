"""Bounded public-CLI workload; opt into the million-record acceptance run."""

import json
import os
import resource
import shutil
import time
import tracemalloc
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import duckdb
from fake_cdp import FakeBrowser

from dogopencli.browser import cdp

ROOT = Path(__file__).resolve().parents[2]


def test_bounded_history_resumes_without_loading_or_refetching_full_history(
    run_cli, tmp_path, monkeypatch
):
    days = int(os.environ.get("DOGOPENCLI_SYNC_SCALE_DAYS", "3"))
    rows_per_day = int(os.environ.get("DOGOPENCLI_SYNC_SCALE_ROWS", "1000"))
    assert days >= 2 and rows_per_day >= 1000 and rows_per_day % 1000 == 0
    start = date(2026, 1, 1)
    end = start + timedelta(days=days - 1)
    interrupted_day = start + timedelta(days=days // 2)
    source = tmp_path / "history"
    shutil.copytree(ROOT / "tools/leaf-dev/example", source)
    manifest_path = source / "leaf.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["operations"].pop("get")
    manifest["operations"]["list"]["parameters"] = [
        {
            "name": name,
            "type": "string",
            "required": True,
            "description": "Inclusive synthetic business date.",
        }
        for name in ("from-date", "to-date")
    ]
    manifest["collection"]["paging"]["page_sizes"] = [1000]
    manifest["sync"] = [
        {
            "variant": "daily",
            "mode": "runtime",
            "key_fields": ["id"],
            "scope_parameters": [],
            "evidence": "Synthetic exact daily total and identity.",
            "time": {
                "start_parameter": "from-date",
                "end_parameter": "to-date",
                "format": "date",
                "timezone": "UTC",
                "max_days": 1,
                "partitionable": True,
                "follow_supported": True,
            },
        }
    ]
    manifest_path.write_text(json.dumps(manifest))
    adapter_path = source / "adapter.py"
    adapter = adapter_path.read_text().replace("page_size=2", "page_size=1000")
    adapter = adapter.replace('fixed_body_values=(("scope", "all"),),', "")
    adapter = adapter.replace('scope != "all" or ', "")
    adapter = adapter.replace(
        'return "all"', 'return parameters["from_date"] + "/" + parameters["to_date"]'
    )
    adapter_path.write_text(adapter)
    config = tmp_path / "config.toml"
    config.write_text(
        f'[auth]\nprofile="{tmp_path / "chrome"}"\ncdp_url="http://127.0.0.1:9222"\n'
    )
    monkeypatch.setenv("DOGOPENCLI_CONFIG", str(config))
    browser = FakeBrowser(href="https://leaf-handbook.invalid/app")
    cdp.set_transport_factory(browser.transport)
    interrupted = False
    fetched_days = []
    maximum_page = 0

    def handler(body, _):
        nonlocal interrupted, maximum_page
        left, right = body["scope"].split("/")
        assert left == right  # Independent native request boundary assertion.
        day = date.fromisoformat(left)
        if day == interrupted_day and not interrupted:
            interrupted = True
            raise KeyboardInterrupt
        if body["pageNo"] == 0:
            fetched_days.append(day)
        offset = body["pageNo"] * body["pageSize"]
        ordinal = (day - start).days * rows_per_day + offset
        rows = [
            {"id": str(i), "ordinal": i, "day": left}
            for i in range(ordinal, ordinal + 1000)
        ]
        if offset == 0:
            rows[0]["native"] = {"amount": Decimal("0.1234567890123456789")}
        maximum_page = max(maximum_page, len(rows))
        return {
            "status": 200,
            "body": {
                "success": True,
                "rows": rows,
                "pageNo": body["pageNo"],
                "pageSize": 1000,
                "total": rows_per_day,
            },
        }

    browser.business_handler = handler
    database = str(tmp_path / "duckdog.duckdb")
    try:
        code, output, _ = run_cli(["plugins", "install", str(source)])
        assert code == 0, output
        tracemalloc.start()
        started = time.perf_counter()
        args = [
            "collection",
            "sync",
            "sample.records",
            "--from-date",
            str(start),
            "--to-date",
            str(end),
        ]
        code, output, _ = run_cli(args)
        assert code == 130, output
        with duckdb.connect(database, read_only=True) as db:
            assert (
                db.execute("SELECT count(*) FROM collection_sample_records").fetchone()[
                    0
                ]
                == (days // 2) * rows_per_day
            )
        first_days = tuple(fetched_days)
        assert first_days == tuple(start + timedelta(days=i) for i in range(days // 2))
        fetched_days.clear()
        code, output, _ = run_cli(["sync"])
        assert code == 0, output
        assert fetched_days == [
            start + timedelta(days=i) for i in range(days // 2, days)
        ]
        elapsed = time.perf_counter() - started
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        total = days * rows_per_day
        with duckdb.connect(database, read_only=True) as db:
            actual = db.execute(
                "SELECT count(*), "
                "count(DISTINCT json_extract_string(_record, '$.id')), "
                "sum(CAST(json_extract_string(_record, '$.ordinal') AS BIGINT)) "
                "FROM collection_sample_records"
            ).fetchone()
            assert actual == (total, total, total * (total - 1) // 2)
            from dogopencli.jsonutil import parse

            first = parse(
                db.execute(
                    "SELECT _record FROM collection_sample_records "
                    "WHERE json_extract_string(_record, '$.id')='0'"
                ).fetchone()[0]
            )
            assert first["native"]["amount"] == Decimal("0.1234567890123456789")
        count = len(browser.business_requests)
        code, output, _ = run_cli(["sync"])
        assert code == 0, output
        assert len(browser.business_requests) == count
        status = json.loads(run_cli(["sync", "status"])[1])["data"]
        assert len(status["coverage"]) == days and status["targets"][0]["gaps"] == []
        assert maximum_page == 1000
        report = {
            "rows": total,
            "days": days,
            "rows_per_chunk": rows_per_day,
            "max_response_rows": maximum_page,
            "elapsed_seconds": round(elapsed, 3),
            "peak_python_bytes": peak,
            "peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            "initial_committed_rows": (days // 2) * rows_per_day,
            "resumed_days": len(fetched_days),
            "final_replay_requests": 0,
        }
        destination = os.environ.get("DOGOPENCLI_SYNC_SCALE_REPORT")
        if destination:
            Path(destination).write_text(json.dumps(report, indent=2) + "\n")
    finally:
        if tracemalloc.is_tracing():
            tracemalloc.stop()
        cdp.set_transport_factory(None)
