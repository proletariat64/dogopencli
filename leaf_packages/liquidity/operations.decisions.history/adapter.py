"""Native decision versions bound to their verified current report lineage."""

from typing import Any

from dogopencli.contracts import EndpointContract
from dogopencli.errors import CliError
from dogopencli.jsonutil import canonical, parse

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

    def __init__(self, name: str, selected: int):
        self.source = name
        self.selected = selected
        self.name = "liquidity.operations.decisions.history." + name
        self.contract = EndpointContract(
            method="POST",
            host="iliquidity.alipay.com",
            path="/api/ai/decision/report/"
            + ("getDetail.json" if name == "root" else "getHistory.json"),
            page_size=0,
            one_based=False,
            allowed_body_keys=frozenset({"tntInstId", "id"}),
            fixed_body_values=(("tntInstId", TENANT),),
        )

    def page_body(self, scope: str, position: int, page_size: int) -> dict:
        selected = report_id(parse(scope))
        if selected != self.selected or position != 0 or page_size != 0:
            fail("source scope differs from selected report", "REQUEST_NOT_ALLOWED")
        return {"tntInstId": TENANT, "id": selected}

    def parse_rows(self, body: bytes) -> tuple[list[dict], None]:
        data = envelope(body)
        if self.source == "root":
            if (
                not isinstance(data, dict)
                or type(data.get("id")) is not int
                or data["id"] != self.selected
            ):
                fail("current detail identity does not match request")
            if any(
                not isinstance(data.get(field), str) or not data[field].strip()
                for field in LINEAGE
            ):
                fail("current detail lineage is missing")
            if data["tntInstId"] != TENANT:
                fail("current detail tenant differs from request")
            return [data], None
        if not isinstance(data, list) or any(not isinstance(row, dict) for row in data):
            fail("history must be a native array of objects")
        for row in data:
            if type(row.get("id")) is not int or type(row.get("version")) is not int:
                fail("history id and version must be native integers")
        return data, None


class Adapter:
    def source_capability(self, name: str, parameters: dict) -> Inquiry:
        selected = report_id(parameters)
        if name not in {"root", "history"}:
            fail("undeclared inquiry", "REQUEST_NOT_ALLOWED")
        return Inquiry(name, selected)

    def source_scope(self, name: str, parameters: dict) -> str:
        self.source_capability(name, parameters)
        return self.scope(parameters)

    def scope(self, parameters: dict) -> str:
        return canonical({"id": report_id(parameters)})

    def assemble(
        self, records_by_source: dict[str, list[dict]], parameters: dict
    ) -> list[dict]:
        current = records_by_source["root"][0]
        rows = records_by_source["history"]
        for row in rows:
            if any(row.get(field) != current[field] for field in LINEAGE):
                fail("history lineage differs from current detail")
        return rows

    def filter(self, records: list[dict], parameters: dict) -> list[dict]:
        return records


adapter = Adapter()
