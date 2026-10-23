"""Independent synthetic parent-only packages for cache compatibility tests."""

import json
import sqlite3
from pathlib import Path

PRIOR_ADAPTER = '''"""Synthetic native-parent List; no dependent source contract."""

from dogopencli.contracts import EndpointContract
from dogopencli.jsonutil import canonical, parse


class Adapter:
    name = "synthetic.forecast.parents"
    page_url = "https://iliquidity.alipay.com/GUAPW3SG/menu/PortfolioMgmt"
    contract = EndpointContract(
        method="GET",
        host="iliquidity.alipay.com",
        path="/bankCashForecastRecordQuery.json",
        page_size=5000,
        one_based=False,
        encoding="query",
        allowed_body_keys=frozenset({"tntInstId", "bankCashForecastRecordQueryVo"}),
        fixed_body_values=(("tntInstId", "GUAPW3SG"),),
        json_body_contracts=((
            "bankCashForecastRecordQueryVo",
            frozenset({"rowStart", "pageSize"}), (), frozenset({5000}),
        ),),
    )

    def capability(self, parameters):
        return self

    def scope(self, parameters):
        return canonical(parameters)

    def filter(self, records, parameters):
        return records

    def page_body(self, scope, row_start, page_size):
        return {
            "tntInstId": "GUAPW3SG",
            "bankCashForecastRecordQueryVo": canonical({
                "rowStart": row_start, "pageSize": page_size,
            }),
        }

    def parse_rows(self, body):
        result = parse(body)["result"]
        return result["dataValue"], result["count"]


adapter = Adapter()
'''


def write_prior_forecast(destination: Path, name: str) -> Path:
    """Create an old output contract without copying the current implementation."""
    destination.mkdir()
    parameters = (
        ("from-date", "to-date")
        if name == "forecast.results"
        else ("account-alias", "record-date")
    )
    manifest = {
        "domain": "liquidity",
        "name": name,
        "adapter": "adapter.py:adapter",
        "summary": "Synthetic parent-only forecast capture.",
        "purpose": "Exercise rejection of a separately saved output contract.",
        "limitations": ["Synthetic prior package; run only with fake CDP responses."],
        "examples": [
            {
                "title": "Read saved parents",
                "command": "dogopencli liquidity list " + name,
            }
        ],
        "operations": {
            "list": {
                "description": "Read native parents in the synthetic test scope.",
                "parameters": [
                    {
                        "name": key,
                        "type": "string",
                        "required": True,
                        "description": "Explicit synthetic scope selector.",
                    }
                    for key in parameters
                ],
            }
        },
        "fields": [{"name": "id", "type": "string", "meaning": "Native parent ID."}],
        "identity": ["id"],
        "identity_description": "Native parent identity.",
        "dataset": {"relation": "liquidity_" + name.replace(".", "_")},
        "collection": {
            "provider": "general",
            "paging": {"mode": "offset", "page_sizes": [5000]},
            "primary_id": {"type": "field", "fields": ["id"]},
        },
    }
    (destination / "leaf.json").write_text(json.dumps(manifest))
    (destination / "adapter.py").write_text(PRIOR_ADAPTER)
    return destination


def copy_cache(source: Path, destination: Path) -> None:
    """Copy a closed acquisition snapshot, including any committed WAL content."""
    with sqlite3.connect(source) as original:
        with sqlite3.connect(destination) as snapshot:
            original.backup(snapshot)
