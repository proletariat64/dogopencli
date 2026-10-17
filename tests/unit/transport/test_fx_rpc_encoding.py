"""Execute shared RPC fetch JavaScript against a local synthetic fetch stub."""

import json
import shutil
import subprocess

import pytest

from dogopencli.contracts import EndpointContract
from dogopencli.transport import QueryRequest
from dogopencli.transport.cdp import _fetch_expression


def test_rpc_wire_body_executes_as_single_element_array():
    node = shutil.which("node")
    if node is None:
        pytest.skip("JavaScript runtime unavailable")
    c = EndpointContract(
        "POST",
        "example.test",
        "/rpc/inquiry",
        50,
        False,
        frozenset({"queryRequest", "pageNo", "pageSize"}),
        encoding="json-array",
        nested_body_keys=(("queryRequest", frozenset({"uniqueIds"})),),
    )
    body = {
        "queryRequest": {"uniqueIds": ["SYNTHETIC-ID"]},
        "pageNo": 0,
        "pageSize": 50,
    }
    request = QueryRequest("sample.rpc", c.method, c.host, c.path, body)
    script = (
        "globalThis.document = {cookie: 'ctoken=synthetic'};"
        "globalThis.fetch = async (url, options) => {"
        "console.log(JSON.stringify({body: JSON.parse(options.body), "
        "method: options.method, credentials: options.credentials}));"
        "return {status: 200, text: async () => '{}', "
        "headers: {get: () => null}, url, redirected: false}; };"
        + _fetch_expression(request, 1, encoding=c.encoding)
    )
    result = subprocess.run(
        [node, "-e", script], capture_output=True, text=True, timeout=5
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {
        "body": [body],
        "method": "POST",
        "credentials": "include",
    }
