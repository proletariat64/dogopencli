"""Execute generated query JS against a real loopback HTTPS redirect server."""

import json
import os
import shutil
import subprocess

import pytest

from dogopencli.transport import QueryRequest
from dogopencli.transport.cdp import _fetch_expression


def test_generated_fetch_never_sends_a_redirect_destination_request(tmp_path):
    node, openssl = shutil.which("node"), shutil.which("openssl")
    if node is None or openssl is None:
        pytest.skip("Local HTTPS fetch proof requires Node and OpenSSL")
    key, certificate = tmp_path / "key.pem", tmp_path / "certificate.pem"
    subprocess.run(
        [
            openssl,
            "req",
            "-x509",
            "-newkey",
            "rsa:2048",
            "-nodes",
            "-keyout",
            str(key),
            "-out",
            str(certificate),
            "-days",
            "1",
            "-subj",
            "/CN=127.0.0.1",
            "-addext",
            "subjectAltName=IP:127.0.0.1",
        ],
        check=True,
        capture_output=True,
        timeout=15,
    )
    cases = [
        {
            "status": status,
            "expression": _fetch_expression(
                QueryRequest(
                    "synthetic.inquiry",
                    "POST",
                    "127.0.0.1:PORT",
                    f"/inquiry/{status}/{destination}",
                    {"synthetic": "body"},
                ),
                2,
            ),
        }
        for status in (200, 301, 302, 303, 307, 308)
        for destination in ("same-origin", "other-origin")
    ]
    script = """
const https = require('node:https');
const fs = require('node:fs');
const events = [], results = [];
const tls = {
  key: fs.readFileSync(process.argv[1]), cert: fs.readFileSync(process.argv[2])
};
const destination = https.createServer(tls, (request, response) => {
  events.push({path: request.url, method: request.method});
  response.end('{"success":true}');
});
const server = https.createServer(tls, (request, response) => {
  let body = '';
  request.on('data', part => body += part);
  request.on('end', () => {
    events.push({path: request.url, method: request.method, body});
    const status = Number(request.url.split('/')[2]);
    if (status >= 300 && status < 400) {
      const origin = request.url.includes('/other-origin')
        ? 'https://127.0.0.1:' + destination.address().port : '';
      response.writeHead(status, {Location: origin + '/unapproved/destination'});
    }
    else response.writeHead(200, {'Content-Type': 'application/json'});
    response.end('{"success":true}');
  });
});
destination.listen(0, '127.0.0.1', () => server.listen(0, '127.0.0.1', async () => {
  globalThis.document = {cookie: ''};
  try {
    for (const item of JSON.parse(process.argv[3])) {
      const expression = item.expression.replaceAll(
        ':PORT', ':' + server.address().port);
      results.push({status: item.status, result: await eval(expression)});
    }
    console.log(JSON.stringify({events, results}));
  } catch (error) { console.error(error); process.exitCode = 1; }
  finally {
    server.closeAllConnections(); server.close();
    destination.closeAllConnections(); destination.close();
  }
}));
"""
    completed = subprocess.run(
        [node, "-e", script, str(key), str(certificate), json.dumps(cases)],
        env={**os.environ, "NODE_EXTRA_CA_CERTS": str(certificate)},
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert completed.returncode == 0, completed.stderr
    proof = json.loads(completed.stdout)
    assert len(proof["events"]) == len(cases)
    assert all(event["path"].startswith("/inquiry/") for event in proof["events"])
    assert all(event["method"] == "POST" for event in proof["events"])
    assert all(
        json.loads(event["body"]) == {"synthetic": "body"} for event in proof["events"]
    )
    for entry in proof["results"]:
        result = entry["result"]
        if entry["status"] == 200:
            assert result["status"] == 200
            assert result["redirected"] is False
        else:
            assert result["status"] == 0
            assert result["error"]
