"""Small synthetic endpoint for exercising shared acquisition mechanics."""

import math
from dataclasses import dataclass

from dogopencli.contracts import EndpointContract, ParsedPage
from dogopencli.jsonutil import parse


@dataclass(frozen=True)
class SyntheticCapability:
    name: str = "sample.rows"
    source_config_key: str = "sample"
    default_scope: str = "sample"
    contract: EndpointContract = EndpointContract(
        "POST",
        "example.test",
        "/inquiry",
        5000,
        False,
        frozenset({"pageNo", "pageSize", "scope"}),
        rebuild_page_size=10000,
        scope_field="scope",
    )

    def page_body(self, scope, page_num, page_size):
        return {"scope": scope, "pageNo": page_num, "pageSize": page_size}

    def parse_page(self, body):
        value = parse(body)
        return ParsedPage(
            value["resultDataList"],
            value["pageNo"],
            value["pageSize"],
            value["totalCount"],
            math.ceil(value["totalCount"] / value["pageSize"]),
        )

    def identity_key(self, row):
        return row["id"]


SAMPLE = SyntheticCapability()
SCOPE = "sample"
