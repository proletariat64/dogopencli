"""Explicit realtime enrichment import; no inquiry cache or production defaults."""

import argparse
import datetime as dt
import decimal
import importlib.util
import json
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from typing import Any

from dogopencli.plugins.liquidity.spec import TENANT

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


def load_owner(path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location("duckdog_settings_owner", path)
    owner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(owner)
    if getattr(owner, "B03_STORAGE_VERSION", None) != 1:
        raise ValueError("settings importer requires B03 owner patch")
    if getattr(owner, "B03_DETAIL_REFRESH", None) is not True:
        raise ValueError("settings importer requires detail refresh ordering patch")
    if getattr(owner, "B03_COMPONENT_ORDERING", None) is not True:
        raise ValueError("settings importer requires component ordering patch")
    return owner


def exact(left: Any, right: Any) -> bool:
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


def effective_detail(row: dict[str, Any]) -> dict[str, Any] | None:
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


def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("conflicting JSON field duplication")
        value[key] = item
    return value


def captured(value: Any) -> None:
    if not isinstance(value, str) or dt.datetime.fromisoformat(value).tzinfo is None:
        raise ValueError("component capture time requires timezone")


def validate_components(
    detail: dict[str, Any], components: Any, owner: ModuleType
) -> None:
    """Bind association proof to acquired detail, independently of the older list."""
    if not isinstance(components, dict):
        raise owner.ImportRejected("invalid component metadata")
    network = components.get("network")
    if not isinstance(network, dict) or (
        not exact(network.get("identity"), {"id": detail["id"]})
        or not exact(network.get("request_scope"), {"id": detail["id"]})
        or network.get("status") != "succeeded"
        or network.get("applicability") != "applicable"
        or network.get("complete") is not True
        or type(network.get("returned_count")) is not int
        or network["returned_count"] != 1
    ):
        raise owner.ImportRejected("network component identity or acquisition conflict")
    captured(network.get("captured_at"))
    if "source_version" in network and not exact(
        network["source_version"], detail.get("version")
    ):
        raise owner.ImportRejected("network component version conflict")
    for name in ASSOCIATIONS:
        component = components.get(name)
        if name not in detail or not isinstance(component, dict):
            raise owner.ImportRejected("missing association or component")
        status = component.get("status")
        payload = detail[name]
        if type(component.get("complete")) is not bool:
            raise owner.ImportRejected("invalid association quality")
        if not isinstance(component.get("reasons"), list):
            raise owner.ImportRejected("missing component reasons")
        if status in {"unverified", "inapplicable"}:
            if (
                any(
                    field not in component
                    for field in (
                        "identity",
                        "request_scope",
                        "captured_at",
                        "returned_count",
                        "reported_count",
                    )
                )
                or payload is not None
                or component.get("applicability") != status
                or any(
                    component.get(field) is not None
                    for field in (
                        "identity",
                        "request_scope",
                        "captured_at",
                        "returned_count",
                        "reported_count",
                    )
                )
                or component["complete"] is (status == "unverified")
            ):
                raise owner.ImportRejected(
                    "unacquired association has acquisition evidence"
                )
            if status == "unverified":
                history_ready = detail.get("scene") == "REALTIME" and all(
                    isinstance(detail.get(field), str) and detail[field].strip()
                    for field in ("creditAliasName", "debitAliasName", "fundAction")
                )
                route_ready = "routeId" in detail and (
                    detail["routeId"] in (None, "")
                    or all(
                        isinstance(detail.get(field), str) and detail[field].strip()
                        for field in ("routeId", "debitAliasName")
                    )
                )
                if history_ready if name == "operationHistory" else route_ready:
                    raise owner.ImportRejected(
                        "verified caller context marked unverified"
                    )
            if status == "inapplicable" and (
                name != "routeDetails"
                or "routeId" not in detail
                or detail["routeId"] not in (None, "")
            ):
                raise owner.ImportRejected("invalid association inapplicability")
            continue
        if status != "succeeded" or component.get("applicability") != "applicable":
            raise owner.ImportRejected("invalid association acquisition")
        captured(component.get("captured_at"))
        if type(component.get("returned_count")) is not int:
            raise owner.ImportRejected("missing association count")
        if name == "operationHistory":
            fields = ("creditAliasName", "debitAliasName", "fundAction")
            if detail.get("scene") != "REALTIME" or any(
                not isinstance(detail.get(field), str) or not detail[field].strip()
                for field in fields
            ):
                raise owner.ImportRejected("history root scope unavailable")
            expected = {
                "creditAliasName": [detail["creditAliasName"]],
                "debitAliasName": [detail["debitAliasName"]],
                "fundAction": detail["fundAction"],
            }
            if (
                not exact(component.get("request_scope"), expected)
                or component.get("identity") is not None
                or not isinstance(payload, list)
                or component["returned_count"] != len(payload)
            ):
                raise owner.ImportRejected("history scope or payload conflict")
            if component.get("native_contract") == "realtime-network-history-v1" and (
                component["complete"] is not False
                or "HISTORY_COVERAGE_UNPROVEN" not in component["reasons"]
            ):
                raise owner.ImportRejected("history coverage is not proven")
            history_identities: dict[tuple[type, str], dict[str, Any]] = {}
            for row in payload:
                if (
                    not isinstance(row, dict)
                    or type(row.get("version")) is not int
                    or not isinstance(row.get("id"), str)
                    or not str(row["id"]).strip()
                    or row.get("scene") != "REALTIME"
                    or any(not exact(row.get(field), detail[field]) for field in fields)
                    or row.get("tntInstId") not in (None, "", TENANT)
                ):
                    raise owner.ImportRejected(
                        "history record contradicts acquired scope"
                    )
                identity = (type(row["id"]), row["id"])
                if identity in history_identities and not exact(
                    history_identities[identity], row
                ):
                    raise owner.ImportRejected("conflicting history identity")
                history_identities[identity] = row
        else:
            expected = {
                "routeId": detail.get("routeId"),
                "aliasName": detail.get("debitAliasName"),
                "tntInstId": TENANT,
            }
            if (
                any(
                    not isinstance(expected[field], str) or not expected[field].strip()
                    for field in ("routeId", "aliasName")
                )
                or not exact(component.get("identity"), expected)
                or not exact(component.get("request_scope"), expected)
                or not isinstance(payload, dict)
                or component["returned_count"] != 1
            ):
                raise owner.ImportRejected(
                    "route association scope or payload conflict"
                )
            if (
                component.get("native_contract") == "route-quota-detail-v1"
                and component["complete"] is not True
            ):
                raise owner.ImportRejected("invalid route aggregate quality")
            for field, value in expected.items():
                if field in payload and not exact(payload[field], value):
                    raise owner.ImportRejected(
                        "native route context contradicts acquired scope"
                    )
            if any(
                not isinstance(payload.get(field), list)
                or any(not isinstance(member, dict) for member in payload[field])
                for field in ("dynamicQuotas", "staticQuotas")
            ):
                raise owner.ImportRejected("invalid route quota members")
            counts = {
                field: len(payload[field])
                for field in ("dynamicQuotas", "staticQuotas")
            }
            if not exact(component.get("member_counts"), counts):
                raise owner.ImportRejected("route member count conflict")
            echoes = {
                field: "present" if field in payload else "absent" for field in expected
            }
            if not exact(component.get("native_context_echo"), echoes):
                raise owner.ImportRejected("route context echo evidence conflict")


def validate_json(text: str, owner: ModuleType) -> None:
    json.loads(
        text,
        parse_float=decimal.Decimal,
        parse_constant=owner.reject_constant,
        object_pairs_hook=unique_object,
    )


def prepare(text: str, owner: ModuleType) -> str:
    validate_json(text, owner)
    rows, meta = owner.validate(text, SELECTOR)
    result, identities = [], set()
    for row in rows:
        if "_detail_storage" in row:
            raise owner.ImportRejected("reserved storage marker collision")
        root = {k: v for k, v in row.items() if k not in RESERVED}
        if not isinstance(root.get("id"), str) or not root["id"].strip():
            raise owner.ImportRejected("realtime native identity must be a string")
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
        detail, detail_meta = row["_detail"], row.get("_detail_meta")
        if not isinstance(detail, dict) or not isinstance(detail_meta, dict):
            raise owner.ImportRejected("invalid detail envelope")
        if (
            type(detail.get("id")) is not type(root["id"])
            or detail.get("id") != root["id"]
        ):
            raise owner.ImportRejected("detail identity conflict")
        if (
            detail_meta.get("capability") != "liquidity.network.realtime.get"
            or detail_meta.get("source") != meta["source"]
            or detail_meta.get("simulated") is not False
            or type(detail_meta.get("returned_count")) is not int
            or detail_meta["returned_count"] != 1
            or type(detail_meta.get("complete")) is not bool
        ):
            raise owner.ImportRejected("invalid detail acquisition")
        stamp = dt.datetime.fromisoformat(detail_meta.get("fetched_at", ""))
        if stamp.tzinfo is None:
            raise owner.ImportRejected("detail capture time requires timezone")
        scope = detail_meta.get("identity")
        if not isinstance(scope, dict) or scope.get("network_id") != str(root["id"]):
            raise owner.ImportRejected("detail scope conflict")
        detail_scope = detail_meta.get("request_scope", {})
        list_scope = meta.get("request_scope", {})
        if not isinstance(detail_scope, dict) or not isinstance(list_scope, dict):
            raise owner.ImportRejected("invalid request scope")
        if not exact(detail_scope, list_scope):
            raise owner.ImportRejected("detail source scope conflict")
        for field in ("tenant", "tenant_id", "instId", "tntInstId", "source_scope"):
            if field in meta or field in detail_meta:
                if (
                    field not in meta
                    or field not in detail_meta
                    or not exact(meta[field], detail_meta[field])
                ):
                    raise owner.ImportRejected("source tenant scope conflict")
            if field in root or field in detail:
                if (
                    field not in root
                    or field not in detail
                    or not exact(root[field], detail[field])
                ):
                    raise owner.ImportRejected("native tenant scope conflict")
        for document in (root, detail, meta, detail_meta, detail_scope, list_scope):
            if "tntInstId" in document and document["tntInstId"] not in (
                None,
                "",
                TENANT,
            ):
                raise owner.ImportRejected("source tenant contradicts application")
        components = detail_meta.get("components")
        if components is not None:
            validate_components(detail, components, owner)
            if detail_meta["complete"] is not all(
                component["complete"] for component in components.values()
            ):
                raise owner.ImportRejected("aggregate quality contradicts components")
        elif detail_meta["complete"] is not True:
            raise owner.ImportRejected("incomplete detail requires component evidence")
        aggregate = bool(ASSOCIATIONS & detail.keys())
        comparable = detail
        decomposable = not aggregate or (
            set(detail) <= ROOT_FIELDS | ASSOCIATIONS
            and set(root) <= ROOT_FIELDS
            and isinstance(detail_meta.get("components"), dict)
            and set(detail_meta["components"]) == {"network", *ASSOCIATIONS}
            and detail_meta["components"]["network"].get("native_contract")
            == "realtime-network-detail-v1"
            and all(
                detail_meta["components"][name].get("native_contract") in allowed
                for name, allowed in (
                    ("operationHistory", (None, "realtime-network-history-v1")),
                    ("routeDetails", (None, "route-quota-detail-v1")),
                )
            )
        )
        if aggregate and decomposable:
            comparable = {k: v for k, v in detail.items() if k in ROOT_FIELDS}
        duplicate = decomposable and exact(root, comparable)
        stored["_detail_meta"] = detail_meta
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


def publish(root: Path, text: str, owner: ModuleType) -> dict[str, Any]:
    return owner.publish(root, SELECTOR, prepare(text, owner))


def acquire(
    text: str,
    owner: ModuleType,
    run: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> str:
    validate_json(text, owner)
    rows, meta = owner.validate(text, SELECTOR)
    for row in rows:
        if not isinstance(row.get("id"), str) or not row["id"].strip():
            raise owner.ImportRejected("realtime native identity must be a string")
        if RESERVED & row.keys():
            raise owner.ImportRejected("reserved enrichment field collision")
    enriched = []
    for row in rows:
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


def main() -> int:
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
