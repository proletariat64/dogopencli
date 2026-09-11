"""Read-only diagnostic: scan EXTERNAL Channel via existing CDP.

Requires websocket-client. Logs counts/codes only; exports records to private files.
Business failures are recorded and traversal continues; this is NOT a cache refresh.
"""

import argparse
import hashlib
import json
import math
import os
import re
import sys
import tempfile
import time
import urllib.request
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import websocket

ORIGIN = "https://ifundbossportal.alipay.com"
ENDPOINT = "https://ifundboss-api.alipay.com/payout/api/ability/search.json"
REPO_ROOT = Path(__file__).resolve().parents[2]
REPO_TMP_ROOT = (REPO_ROOT / "tmp").resolve()


class CDP:
    def __init__(self, port):
        with urllib.request.urlopen(
            f"http://127.0.0.1:{port}/json/list", timeout=5
        ) as r:
            targets = json.load(r)
        target = next(
            t
            for t in targets
            if t.get("type") == "page"
            and t.get("url", "").startswith(
                "https://ifundcontrol.alipay.com/productOperation/paymentProductManagement/networkConstruction/channelsManagement"
            )
        )
        self.ws = websocket.create_connection(
            target["webSocketDebuggerUrl"], timeout=25, suppress_origin=True
        )
        self.seq = 0
        self.contexts = {}
        self.call("Runtime.enable")
        self.context = next(
            c["id"]
            for c in self.contexts.values()
            if c.get("origin") == ORIGIN and c.get("auxData", {}).get("isDefault")
        )

    def call(self, method, params=None):
        self.seq += 1
        self.ws.send(
            json.dumps({"id": self.seq, "method": method, "params": params or {}})
        )
        deadline = time.monotonic() + 25
        while time.monotonic() < deadline:
            self.ws.settimeout(max(0.1, deadline - time.monotonic()))
            m = json.loads(self.ws.recv())
            if m.get("method") == "Runtime.executionContextCreated":
                c = m["params"]["context"]
                self.contexts[c["id"]] = c
            if m.get("id") == self.seq:
                if "error" in m or "exceptionDetails" in m.get("result", {}):
                    raise RuntimeError("CDP command failed; details suppressed")
                return m.get("result", {})
        raise TimeoutError("CDP timeout")

    def query(self, page, page_size=50):
        js = (
            r"""(async()=>{
          if(location.origin!==ORIGIN)return {error:'context_changed'};
          const url=new URL(ENDPOINT);
          const cookie=document.cookie.split(';').map(v=>v.trim()).find(v=>v.startsWith('ctoken='));
          if(cookie)url.searchParams.set('ctoken',decodeURIComponent(cookie.slice(7)));
          try {
            const r=await fetch(url.toString(),{method:'POST',credentials:'include',
              headers:{'Content-Type':'application/json;charset=UTF-8','Accept':'application/json'},
              body:JSON.stringify({payoutType:'EXTERNAL',pageNum:PAGE,pageSize:SIZE}),
              signal:AbortSignal.timeout(20000)});
            return {http:r.status,redirected:r.redirected,text:await r.text()};
          } catch(e){return {error:'fetch_failed'};}
        })()""".replace("ORIGIN", json.dumps(ORIGIN))
            .replace("ENDPOINT", json.dumps(ENDPOINT))
            .replace("PAGE", str(page))
            .replace("SIZE", str(page_size))
        )
        result = self.call(
            "Runtime.evaluate",
            {
                "contextId": self.context,
                "expression": js,
                "awaitPromise": True,
                "returnByValue": True,
            },
        )
        return result["result"]["value"]


def encode_json(value):
    """Preserve numeric JSON values without converting Decimal to strings/floats."""
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return (
            "{"
            + ",".join(json.dumps(k) + ":" + encode_json(v) for k, v in value.items())
            + "}"
        )
    if isinstance(value, list):
        return "[" + ",".join(encode_json(v) for v in value) + "]"
    return json.dumps(value, ensure_ascii=False, allow_nan=False)


def append_records(rows, output, next_seqid):
    if any("seqid" in row for row in rows):
        raise ValueError("Source seqid collision")
    for row in rows:
        output.write(encode_json({"seqid": next_seqid, **row}) + "\n")
        next_seqid += 1
    output.flush()
    return next_seqid


def observe(page, transport, seen, page_size=50):
    info = {"page": page, "http": transport.get("http"), "rows_observed": 0}
    if transport.get("error"):
        return {**info, "outcome": transport["error"]}
    if transport.get("redirected") or transport.get("http") in (401, 403):
        return {**info, "outcome": "auth_or_redirect"}
    try:
        data = json.loads(transport["text"], parse_float=Decimal)
        obj = data.get("resultObj") or {}
        rows = obj.get("payoutAbilityVOList")
        info["rows_observed"] = len(rows) if isinstance(rows, list) else 0
        code = data.get("msgCode")
        info["msgCode"] = (
            code
            if isinstance(code, str) and re.fullmatch(r"[A-Z0-9_]{0,80}", code)
            else None
        )
        if not (
            transport["http"] == 200
            and data.get("success") is True
            and data.get("status") is True
            and obj.get("success") is True
        ):
            return {**info, "outcome": "http_or_business_failure"}
        total, pages = obj["totalCount"], obj["totalPages"]
        if not (
            type(total) is int
            and total >= 0
            and type(pages) is int
            and pages == math.ceil(total / page_size)
            and obj["pageSize"] == page_size
            and obj["pageNum"] == page
            and isinstance(rows, list)
        ):
            return {**info, "outcome": "metadata_invalid"}
        if any(
            type(r.get("abilityId")) is not int or r.get("payoutType") != "EXTERNAL"
            for r in rows
        ):
            return {**info, "outcome": "row_schema_invalid"}
        duplicates = conflicts = 0
        for row in rows:
            ident = row["abilityId"]
            fingerprint = hashlib.sha256(
                json.dumps(row, sort_keys=True, default=str).encode()
            ).digest()
            if ident in seen:
                duplicates += 1
                conflicts += seen[ident] != fingerprint
            else:
                seen[ident] = fingerprint
        return {
            **info,
            "outcome": "success",
            "total": total,
            "pages": pages,
            "unique_in_page": len({r["abilityId"] for r in rows}),
            "duplicates": duplicates,
            "conflicts": conflicts,
            "expected_rows_match": len(rows)
            == min(page_size, max(0, total - (page - 1) * page_size)),
        }
    except (ValueError, TypeError, KeyError, AttributeError):
        return {**info, "outcome": "schema_or_parse_failure"}


def make_export_dir(output_root=None):
    """Create a private export directory, outside the repository when explicit."""
    if output_root is None:
        export_dir = Path(tempfile.mkdtemp(prefix="dogopencli-channel-export-"))
    else:
        root = Path(output_root).expanduser().resolve()
        inside_repo = root == REPO_ROOT or REPO_ROOT in root.parents
        inside_repo_tmp = root == REPO_TMP_ROOT or REPO_TMP_ROOT in root.parents
        if inside_repo and not inside_repo_tmp:
            raise ValueError("--output-root inside the repository must be under tmp")
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(root, 0o700)
        export_dir = Path(
            tempfile.mkdtemp(prefix="dogopencli-channel-export-", dir=root)
        )
    os.chmod(export_dir, 0o700)
    return export_dir


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=9222)
    parser.add_argument("--page-size", type=int, choices=(1, 10, 50, 100), default=50)
    parser.add_argument("--max-pages", type=int, default=200)
    parser.add_argument("--budget-seconds", type=int, default=600)
    parser.add_argument(
        "--output-root",
        type=Path,
        help="Persistent export parent outside the repository (default: system /tmp)",
    )
    args = parser.parse_args()
    if not (1 <= args.port <= 65535) or 9330 <= args.port <= 9340:
        parser.error("Forbidden or invalid CDP port")
    if not (1 <= args.max_pages <= 1000 and 1 <= args.budget_seconds <= 1800):
        parser.error("Invalid diagnostic bounds")
    try:
        export_dir = make_export_dir(args.output_root)
    except (OSError, ValueError) as e:
        parser.error(str(e))
    start = time.monotonic()
    results, seen = [], {}
    fd = os.open(
        export_dir / "records.jsonl", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600
    )
    output = os.fdopen(fd, "w", encoding="utf-8")
    next_seqid = 1
    cdp = None
    stop = "page_bound"
    try:
        cdp = CDP(args.port)
        target_pages = None
        for page in range(1, args.max_pages + 1):
            if time.monotonic() - start >= args.budget_seconds:
                stop = "time_bound"
                break
            transport = cdp.query(page, args.page_size)
            item = observe(page, transport, seen, args.page_size)
            if item["outcome"] == "success":
                rows = json.loads(transport["text"], parse_float=Decimal)["resultObj"][
                    "payoutAbilityVOList"
                ]
                item["seqid_start"] = next_seqid if rows else None
                next_seqid = append_records(rows, output, next_seqid)
                item["seqid_end"] = next_seqid - 1 if rows else None
            results.append(item)
            print(json.dumps({"type": "page", **item}), flush=True)
            if item["outcome"] == "success":
                target_pages = item["pages"] if target_pages is None else target_pages
            if item["outcome"] in (
                "auth_or_redirect",
                "schema_or_parse_failure",
                "row_schema_invalid",
                "metadata_invalid",
                "context_changed",
            ):
                stop = item["outcome"]
                break
            if target_pages is not None and page >= target_pages:
                stop = "traversed_reported_pages"
                break
            time.sleep(0.15)
    except KeyboardInterrupt:
        stop = "interrupted"
    except (
        OSError,
        RuntimeError,
        ValueError,
        KeyError,
        StopIteration,
        websocket.WebSocketException,
    ) as e:
        stop = "runtime_" + type(e).__name__
    finally:
        output.close()
        if cdp:
            cdp.ws.close()
    good = [p for p in results if p["outcome"] == "success"]
    failed = [p["page"] for p in results if p["outcome"] != "success"]
    totals = sorted({p["total"] for p in good})
    complete = (
        stop == "traversed_reported_pages"
        and not failed
        and len(totals) == 1
        and len(seen) == totals[0]
        and all(p["expected_rows_match"] for p in good)
        and not any(p["conflicts"] for p in good)
    )
    summary = {
        "type": "summary",
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "page_size": args.page_size,
        "scope": "EXTERNAL",
        "stop": stop,
        "pages_attempted": len(results),
        "successful_pages": len(good),
        "failed_pages": failed,
        "reported_totals": totals,
        "rows": sum(p["rows_observed"] for p in good),
        "unique_ids": len(seen),
        "duplicates": sum(p["duplicates"] for p in good),
        "conflicts": sum(p["conflicts"] for p in good),
        "complete": complete,
        "elapsed_seconds": round(time.monotonic() - start, 2),
    }
    summary.update(
        {
            "export_dir": str(export_dir),
            "exported_rows": next_seqid - 1,
            "seqid_scope": "this_export_only",
            "duplicates_retained": True,
            "cache_published": False,
        }
    )
    fd = os.open(
        export_dir / "manifest.json", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600
    )
    with os.fdopen(fd, "w", encoding="utf-8") as manifest:
        json.dump({"summary": summary, "pages": results}, manifest, indent=2)
        manifest.write("\n")
    print(json.dumps(summary), flush=True)
    return 0 if complete else (130 if stop == "interrupted" else 1)


if __name__ == "__main__":
    sys.exit(main())
