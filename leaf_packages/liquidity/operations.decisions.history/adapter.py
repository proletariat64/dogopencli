"""Native decision versions bound to their verified current report lineage."""

from typing import Any

from dogopencli.contracts import EndpointContract
from dogopencli.errors import CliError
from dogopencli.jsonutil import canonical, parse
from dogopencli.leaves.query import CustomListResult
from dogopencli.result_policy import AcquisitionEvidence

TENANT = "GUAPW3SG"
LINEAGE = ("reportId", "groupId", "tntInstId")


def fail(message: str, code: str = "INVALID_RESPONSE") -> None:
    raise CliError(
        code,
        "decision history: " + message,
        exit_code=2 if code == "INVALID_ARGUMENT" else 1,
    )


def report_id(parameters: dict) -> int:
    value = parameters.get("id")
    if type(value) is not int:
        fail("one native integer current report id is required", "INVALID_ARGUMENT")
    return value


def envelope(body: bytes) -> Any:
    document = parse(body)
    if not isinstance(document, dict) or type(document.get("success")) is not bool:
        fail("native response requires boolean success")
    if not document["success"]:
        fail("native inquiry failed", "BUSINESS_QUERY_FAILED")
    return document.get("data")


class Inquiry:
    page_url = "https://iliquidity.alipay.com/GUAPW3SG/menu/PortfolioMgmt"

    def __init__(self, name: str):
        self.name = "liquidity.operations.decisions.history." + name
        self.contract = EndpointContract(
            method="POST",
            host="iliquidity.alipay.com",
            path="/api/ai/decision/report/"
            + ("getDetail.json" if name == "root" else "getHistory.json"),
            page_size=0,
            one_based=False,
            single_page=True,
            allowed_body_keys=frozenset({"tntInstId", "id"}),
            fixed_body_values=(("tntInstId", TENANT),),
        )

    def request_body(self, parameters: dict, identity: str | None = None) -> dict:
        selected = report_id(parameters)
        if identity is not None and identity != str(selected):
            fail("detail lookup differs from selected report", "REQUEST_NOT_ALLOWED")
        return {"tntInstId": TENANT, "id": selected}

    def parse_detail(self, body: bytes, parameters: dict, identity: str) -> dict:
        self.request_body(parameters, identity)
        current = envelope(body)
        if (
            not isinstance(current, dict)
            or type(current.get("id")) is not int
            or current["id"] != report_id(parameters)
        ):
            fail("current detail identity does not match request")
        if any(
            not isinstance(current.get(field), str) or not current[field].strip()
            for field in LINEAGE
        ):
            fail("current detail lineage is missing")
        if current["tntInstId"] != TENANT:
            fail("current detail tenant differs from request")
        return current

    def parse_inquiry(self, body: bytes, parameters: dict) -> list[dict]:
        self.request_body(parameters)
        rows = envelope(body)
        if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
            fail("history must be a native array of objects")
        return rows


class Adapter:
    def query_capability(self, operation: str, name: str, parameters: dict) -> Inquiry:
        report_id(parameters)
        if operation != "list" or name not in {"root", "history"}:
            fail("undeclared inquiry", "REQUEST_NOT_ALLOWED")
        return Inquiry(name)

    def scope(self, parameters: dict) -> str:
        return canonical({"id": report_id(parameters)})

    def query_list(self, parameters: dict, tools: Any) -> CustomListResult:
        current = tools.detail("root", str(report_id(parameters)))
        rows = tools.inquire("history")
        seen = set()
        for row in rows:
            if any(row.get(field) != current[field] for field in LINEAGE):
                fail("history lineage differs from current detail")
            if type(row.get("id")) is not int or type(row.get("version")) is not int:
                fail("history id and version must be native integers")
            if row["id"] in seen:
                fail("duplicate history identity")
            seen.add(row["id"])
        evidence = AcquisitionEvidence.for_collection(
            complete=True,
            reported_total=None,
            collected_total=len(rows),
            arrivals=len(rows),
            total_semantics="unknown",
            coverage_basis="qualified_single_response",
            attempts=(
                {
                    "composition": "native-report-lineage",
                    "current_detail_verified": True,
                    "history_lineage_verified": True,
                    "history_returned_count": len(rows),
                    "completion_boundary": "native-history-array",
                    "snapshot_consistency": "sequential inquiries",
                },
            ),
        )
        return CustomListResult(rows, evidence)

    def filter(self, records: list[dict], parameters: dict) -> list[dict]:
        return records


adapter = Adapter()
