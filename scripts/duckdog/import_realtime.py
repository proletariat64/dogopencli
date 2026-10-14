"""Explicit realtime enrichment import; no inquiry cache or production defaults."""

import argparse
import datetime as dt
import decimal
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

SELECTOR = "liquidity/network/realtime"
ROOT_FIELDS = frozenset(
    (
        "id routeId version scene fundAction debitAliasName debitBankId "
        "debitCurrency debitLegalEntityCode creditAliasName creditBankId "
        "creditCurrency creditLegalEntityCode clearingNetworkName clearingNetworkType "
        "networkStatus runStatus processStatus operationCalendar operationDateType "
        "operationTime operationTool singlePaymentLimit timeZone gmtCreate gmtModified"
    ).split()
)
ASSOCIATIONS = frozenset(("operationHistory", "routeDetails"))
RESERVED = frozenset(("_detail", "_detail_meta", "_detail_storage"))


def load_owner(path):
    spec = importlib.util.spec_from_file_location("duckdog_settings_owner", path)
    owner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(owner)
    if getattr(owner, "B03_STORAGE_VERSION", None) != 1:
        raise ValueError("settings importer requires B03 owner patch")
    return owner


def exact(left, right):
    """JSON number equality without bool coercion, float conversion or key order."""
    if isinstance(left, bool) or isinstance(right, bool):
        return type(left) is type(right) and left == right
    if isinstance(left, (int, decimal.Decimal)) and isinstance(
        right, (int, decimal.Decimal)
    ):
        return left == right
    if type(left) is not type(right):
        return False
    if isinstance(left, dict):
        return left.keys() == right.keys() and all(
            exact(left[k], right[k]) for k in left
        )
    if isinstance(left, list):
        return len(left) == len(right) and all(
            exact(a, b) for a, b in zip(left, right, strict=True)
        )
    return left == right


def effective_detail(row):
    """Read legacy rows and version 1 rows without rewriting either."""
    marker = row.get("_detail_storage")
    if marker is None:
        return row.get("_detail")
    if marker.get("version") != 1:
        raise ValueError("unsupported storage version")
    if marker["state"] == "absent":
        return None
    if marker["state"] == "full":
        return row["_detail"]
    if marker["state"] != "record":
        raise ValueError("unsupported detail state")
    root = {k: v for k, v in row.items() if k not in RESERVED}
    return dict(root, **row.get("_detail", {}))


def unique_object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("conflicting JSON field duplication")
        value[key] = item
    return value


def prepare(text, owner):
    json.loads(
        text,
        parse_float=decimal.Decimal,
        parse_constant=owner.reject_constant,
        object_pairs_hook=unique_object,
    )
    rows, meta = owner.validate(text, SELECTOR)
    result, identities = [], set()
    for row in rows:
        if "_detail_storage" in row:
            raise owner.ImportRejected("reserved storage marker collision")
        root = {k: v for k, v in row.items() if k not in RESERVED}
        identity = (type(root["id"]), root["id"])
        if identity in identities:
            raise owner.ImportRejected("duplicate native identity")
        identities.add(identity)
        stored = dict(root)
        if "_detail" not in row:
            if "_detail_meta" in row:
                raise owner.ImportRejected("metadata without acquired detail")
            stored["_detail_storage"] = {"version": 1, "state": "absent"}
            result.append(stored)
            continue
        detail, dm = row["_detail"], row.get("_detail_meta")
        if not isinstance(detail, dict) or not isinstance(dm, dict):
            raise owner.ImportRejected("invalid detail envelope")
        if (
            type(detail.get("id")) is not type(root["id"])
            or detail.get("id") != root["id"]
        ):
            raise owner.ImportRejected("detail identity conflict")
        if (
            dm.get("capability") != "liquidity.network.realtime.get"
            or dm.get("source") != meta["source"]
            or dm.get("simulated") is not False
            or type(dm.get("returned_count")) is not int
            or dm["returned_count"] != 1
            or type(dm.get("complete")) is not bool
        ):
            raise owner.ImportRejected("invalid detail acquisition")
        stamp = dt.datetime.fromisoformat(dm.get("fetched_at", ""))
        if stamp.tzinfo is None:
            raise owner.ImportRejected("detail capture time requires timezone")
        scope = dm.get("identity")
        if not isinstance(scope, dict) or scope.get("network_id") != str(root["id"]):
            raise owner.ImportRejected("detail scope conflict")
        detail_scope = dm.get("request_scope", {})
        list_scope = meta.get("request_scope", {})
        if not isinstance(detail_scope, dict) or not isinstance(list_scope, dict):
            raise owner.ImportRejected("invalid request scope")
        if not exact(detail_scope, list_scope):
            raise owner.ImportRejected("detail source scope conflict")
        for field in ("tenant", "tenant_id", "instId", "source_scope"):
            if field in meta or field in dm:
                if (
                    field not in meta
                    or field not in dm
                    or not exact(meta[field], dm[field])
                ):
                    raise owner.ImportRejected("source tenant scope conflict")
            if field in root or field in detail:
                if (
                    field not in root
                    or field not in detail
                    or not exact(root[field], detail[field])
                ):
                    raise owner.ImportRejected("native tenant scope conflict")
        components = dm.get("components")
        if components is not None:
            if not isinstance(components, dict):
                raise owner.ImportRejected("invalid component metadata")
            network = components.get("network")
            if not isinstance(network, dict):
                raise owner.ImportRejected("missing network component")
            if (
                not exact(network.get("identity"), {"id": root["id"]})
                or not exact(network.get("request_scope"), {"id": root["id"]})
                or network.get("status") != "succeeded"
                or network.get("complete") is not True
            ):
                raise owner.ImportRejected(
                    "network component identity or scope conflict"
                )
            for name in ASSOCIATIONS:
                component = components.get(name)
                if not isinstance(component, dict):
                    raise owner.ImportRejected("missing association component")
                if component.get("status") not in {
                    "succeeded",
                    "unverified",
                    "inapplicable",
                }:
                    raise owner.ImportRejected("invalid association acquisition")
                if type(component.get("complete")) is not bool:
                    raise owner.ImportRejected("invalid association quality")
        elif dm["complete"] is not True:
            raise owner.ImportRejected("incomplete detail requires component evidence")
        aggregate = bool(ASSOCIATIONS & detail.keys())
        comparable = detail
        decomposable = not aggregate or (
            set(detail) <= ROOT_FIELDS | ASSOCIATIONS
            and set(root) <= ROOT_FIELDS
            and isinstance(dm.get("components"), dict)
            and set(dm["components"]) == {"network", *ASSOCIATIONS}
            and dm["components"]["network"].get("native_contract")
            == "realtime-network-detail-v1"
        )
        if aggregate and decomposable:
            comparable = {k: v for k, v in detail.items() if k in ROOT_FIELDS}
        duplicate = decomposable and exact(root, comparable)
        stored["_detail_meta"] = dm
        stored["_detail_storage"] = {
            "version": 1,
            "state": "record" if duplicate else "full",
        }
        if duplicate and aggregate:
            stored["_detail"] = {k: v for k, v in detail.items() if k in ASSOCIATIONS}
        elif not duplicate:
            stored["_detail"] = detail
        if not exact(effective_detail(stored), detail):
            raise owner.ImportRejected("detail reconstruction mismatch")
        result.append(stored)
    # The source list metadata remains complete; detail quality is retained separately.
    return owner.encode({"data": result, "meta": meta})


def publish(root, text, owner):
    return owner.publish(root, SELECTOR, prepare(text, owner))


def acquire(text, owner, run=subprocess.run):
    rows, meta = owner.validate(text, SELECTOR)
    enriched = []
    for row in rows:
        if RESERVED & row.keys():
            raise owner.ImportRejected("reserved enrichment field collision")
        command = [
            "dogopencli",
            "liquidity",
            "network",
            "realtime",
            "get",
            "--network-id",
            str(row["id"]),
            "--format",
            "json",
        ]
        process = run(command, capture_output=True, text=True, timeout=120)
        if process.returncode:
            raise owner.ImportRejected("detail inquiry failed")
        envelope = json.loads(
            process.stdout,
            parse_float=decimal.Decimal,
            parse_constant=owner.reject_constant,
            object_pairs_hook=unique_object,
        )
        if not isinstance(envelope, dict) or envelope.get("error") is not None:
            raise owner.ImportRejected("detail inquiry envelope rejected")
        enriched.append(
            dict(row, _detail=envelope.get("data"), _detail_meta=envelope.get("meta"))
        )
    return owner.encode({"data": enriched, "meta": meta})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--settings-importer", required=True, type=Path)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--input", type=Path, help="Saved enriched live envelope")
    modes.add_argument(
        "--list-input", type=Path, help="Saved list; acquire live detail"
    )
    args = parser.parse_args()
    try:
        owner = load_owner(args.settings_importer)
        text = (args.input or args.list_input).read_text(encoding="utf-8")
        if args.list_input:
            text = acquire(text, owner)
        print(json.dumps(publish(args.root, text, owner)))
    except Exception as error:
        print(
            json.dumps({"error": type(error).__name__, "published": False}),
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
