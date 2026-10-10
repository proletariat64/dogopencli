"""Quiet polling must never disturb tabs or claim a verified login."""

import json
import shutil
import subprocess

import pytest

import dogopencli.browser.login as login_mod
from dogopencli.browser import cdp
from dogopencli.browser.environment import PAYMENT_STARTUP_URL, BrowserEnvironment
from dogopencli.browser.errors import AuthError
from dogopencli.browser.probe import _FETCH_SIGNAL, probe_login_completion


class Session:
    def __init__(self, transport):
        self.transport = transport
        self.closed = False

    def evaluate(self, expression, timeout):
        self.transport.expressions.append(expression)
        self.transport.waits.append(timeout)
        if self.transport.error:
            raise cdp.CdpError("context destroyed")
        return self.transport.result

    def navigate(self, *_args):
        pytest.fail("human-wait probe must never navigate")

    def close(self):
        self.closed = True


class Transport:
    def __init__(self):
        self.result = {"state": "pending"}
        self.error = False
        self.running = True
        self.targets = [
            {
                "type": "page",
                "url": "https://ipaybuservice.alipay.com/login.htm",
                "webSocketDebuggerUrl": "ws://fake/human",
            }
        ]
        self.expressions = []
        self.waits = []
        self.session = Session(self)

    def version(self, *, timeout=None):
        if not self.running:
            raise cdp.CdpError("connection refused")
        return {"User-Agent": "Chrome/128"}

    def list_targets(self, *, timeout):
        self.waits.append(timeout)
        return self.targets

    def open_session(self, ws_url, *, timeout):
        assert ws_url == "ws://fake/human"
        self.waits.append(timeout)
        return self.session

    def new_target(self, *_args, **_kwargs):
        pytest.fail("human-wait probe must never open a tab")

    def close_target(self, *_args):
        pytest.fail("human-wait probe must never close a tab")


@pytest.fixture
def setup(tmp_path, monkeypatch):
    env = BrowserEnvironment(
        cdp_url="http://127.0.0.1:9224",
        profile=tmp_path / "chrome",
        startup_url=PAYMENT_STARTUP_URL,
        chrome_bin="google-chrome",
        log_path=tmp_path / "chrome.log",
    )
    transport = Transport()
    monkeypatch.setattr("dogopencli.browser.probe.make_transport", lambda _: transport)
    return env, transport


@pytest.mark.parametrize(
    ("result", "code"),
    [
        ({"state": "pending"}, "auth_required"),
        ({"state": "inconclusive"}, "service_failure"),
        ({"status": 200}, "service_failure"),
        (None, "service_failure"),
        ({"state": True}, "service_failure"),
    ],
)
def test_signal_classification_closes_only_websocket(setup, result, code):
    env, transport = setup
    transport.result = result
    with pytest.raises(AuthError) as caught:
        probe_login_completion(env)
    assert caught.value.code == code
    assert transport.session.closed
    assert all(0 < t <= 15 for t in transport.waits)


def test_completion_is_only_a_signal(setup):
    env, transport = setup
    transport.result = {"state": "complete"}
    assert probe_login_completion(env) is None  # no authenticated verdict
    assert transport.session.closed
    (expression,) = transport.expressions
    assert 'redirect: "manual"' in expression
    assert 'credentials: "include"' in expression
    assert 'cache: "no-store"' in expression
    assert 'method: "GET"' in expression


@pytest.mark.parametrize("kind", ["closed", "unrelated", "iframe", "lookalike"])
def test_no_suitable_carrier_does_not_create_tab(setup, kind):
    env, transport = setup
    if kind == "closed":
        transport.targets = []
    elif kind == "unrelated":
        transport.targets[0]["url"] = "https://unrelated.example/"
    elif kind == "iframe":
        transport.targets[0]["type"] = "iframe"
    else:
        transport.targets[0]["url"] = "https://ipaybuservice.alipay.com.evil.example/"
    with pytest.raises(AuthError) as caught:
        probe_login_completion(env)
    assert caught.value.code == "service_failure"
    assert transport.expressions == []


def test_transitioning_target_is_retryable_not_browser_loss(setup):
    env, transport = setup
    transport.error = True
    with pytest.raises(AuthError) as caught:
        probe_login_completion(env)
    assert caught.value.code == "service_failure"
    assert transport.session.closed


@pytest.mark.parametrize("elapsed", [1.0, 0.999])
def test_fetch_timeout_is_not_proof_of_browser_loss(setup, monkeypatch, elapsed):
    env, transport = setup
    clock = [0.0]
    versions = []
    monkeypatch.setattr("dogopencli.browser.probe.monotonic", lambda: clock[0])

    def version(*, timeout=None):
        assert timeout is not None
        versions.append(timeout)
        if timeout < 0.01:
            raise cdp.CdpError("healthy Chrome cannot reply within 1ms")
        return {"User-Agent": "Chrome/128"}

    def evaluate(expression, timeout):
        clock[0] = elapsed
        raise cdp.CdpError("fetch consumed its wait budget")

    monkeypatch.setattr(transport, "version", version)
    monkeypatch.setattr(transport.session, "evaluate", evaluate)
    with pytest.raises(AuthError) as caught:
        probe_login_completion(env, timeout=1.0)
    assert caught.value.code == "service_failure"
    assert versions == [1.0]
    assert transport.session.closed


@pytest.mark.parametrize("budget", [0.001, 0.5, 0.999])
def test_initial_short_reachability_timeout_is_inconclusive(setup, monkeypatch, budget):
    env, transport = setup
    versions = []
    monkeypatch.setattr("dogopencli.browser.probe.monotonic", lambda: 0.0)

    def version(*, timeout=None):
        versions.append(timeout)
        raise cdp.CdpError("healthy Chrome cannot reply within this short budget")

    monkeypatch.setattr(transport, "version", version)
    with pytest.raises(AuthError) as caught:
        probe_login_completion(env, timeout=budget)
    assert caught.value.code == "service_failure"
    assert versions == [budget]
    assert transport.running
    assert transport.expressions == []


def test_browser_loss_aborts_wait(setup):
    env, transport = setup
    transport.running = False
    with pytest.raises(AuthError) as caught:
        probe_login_completion(env)
    assert caught.value.code == "browser_unavailable"


@pytest.mark.parametrize("state", ["pending", "inconclusive"])
def test_wait_timeout_preserves_failure_class_and_respects_deadline(
    setup, monkeypatch, state
):
    env, transport = setup
    transport.result = {"state": state}
    clock = [0.0]
    monkeypatch.setattr(login_mod, "monotonic", lambda: clock[0])
    monkeypatch.setattr(
        login_mod, "sleep", lambda seconds: clock.__setitem__(0, clock[0] + seconds)
    )
    with pytest.raises(AuthError) as caught:
        login_mod._wait_for_human_auth(env, deadline=0.1)
    assert caught.value.code == (
        "auth_required" if state == "pending" else "service_failure"
    )
    assert clock[0] == pytest.approx(0.1)
    assert len(transport.expressions) == 1


def test_http_target_discovery_validates_inventory(monkeypatch):
    transport = cdp.HttpCdpTransport("http://127.0.0.1:9224")
    monkeypatch.setattr(transport, "_get_json", lambda *_a, **_k: {"targets": []})
    with pytest.raises(cdp.CdpError):
        transport.list_targets()


def test_probe_setup_shares_wait_budget(setup, monkeypatch):
    env, transport = setup
    clock = [0.0]
    monkeypatch.setattr("dogopencli.browser.probe.monotonic", lambda: clock[0])
    original = transport.list_targets

    def discover(*, timeout):
        result = original(timeout=timeout)
        clock[0] += 0.6
        return result

    monkeypatch.setattr(transport, "list_targets", discover)
    with pytest.raises(AuthError):
        probe_login_completion(env, timeout=1.0)
    assert transport.waits == pytest.approx([1.0, 0.4, 0.4])


@pytest.mark.skipif(
    shutil.which("node") is None, reason="optional JS runtime unavailable"
)
@pytest.mark.parametrize(
    ("response", "expected"),
    [
        (
            {"body": {"success": False, "buserviceErrorCode": "USER_NOT_LOGIN"}},
            "pending",
        ),
        ({"body": {"data": {"outUserNo": "SANITIZED"}}}, "complete"),
        ({"body": {"data": {"outUserNo": 123}}}, "complete"),
        (
            {
                "origin": "https://ipaybuservice.alipay.com",
                "body": {"data": {"outUserNo": 123}},
            },
            "inconclusive",  # global SSO alone must not interrupt the form
        ),
        (
            {"readyState": "loading", "body": {"data": {"outUserNo": 123}}},
            "inconclusive",
        ),
        ({"body": {"data": {"outUserNo": " "}}}, "inconclusive"),
        ({"body": {"data": {"outUserNo": False}}}, "inconclusive"),
        ({"body": {"data": {"unexpected": "shape"}}}, "inconclusive"),
        ({"body": {"data": []}}, "inconclusive"),
        ({"body": {"data": None}}, "inconclusive"),
        ({"body": {"stat": "fail", "msg": "RefererCheckFailed"}}, "inconclusive"),
        ({"body": {"success": False, "data": {"outUserNo": 123}}}, "inconclusive"),
        ({"status": 503, "body": {"data": {"outUserNo": 123}}}, "inconclusive"),
        ({"status": 0, "url": ""}, "inconclusive"),
        ({"jsonError": True}, "inconclusive"),
        ({"error": True}, "inconclusive"),
        ({"origin": "https://unrelated.example"}, "inconclusive"),
        ({"body": {}}, "inconclusive"),
    ],
)
def test_fetch_javascript_does_not_confuse_200_with_auth(response, expected):
    # Run the actual in-page expression against sanitized fetch responses.
    # Node is optional; core Python tests remain independent of JS tooling.
    expression = _FETCH_SIGNAL.replace(
        "__PAYLOAD__",
        json.dumps(
            {
                "url": PAYMENT_STARTUP_URL,
                "origins": [
                    "https://ipaybuservice.alipay.com",
                    "https://ifundcontrol.alipay.com",
                ],
                "applicationOrigin": "https://ifundcontrol.alipay.com",
                "timeoutMs": 100,
            }
        ),
    )
    script = r"""
    const vm = require('node:vm');
    const input = JSON.parse(require('node:fs').readFileSync(0, 'utf8'));
    const r = input.response;
    const sandbox = {
      location: {origin: r.origin || 'https://ifundcontrol.alipay.com'},
      document: {readyState: r.readyState || 'complete'},
      AbortController, setTimeout, clearTimeout,
      fetch: async (url, options) => {
        if (r.error) throw new TypeError('CORS or network failure');
        if (options.redirect !== 'manual' || options.credentials !== 'include')
          throw new Error('unsafe fetch options');
        return {
          status: r.status ?? 200, url: r.url ?? url,
          json: async () => {
            if (r.jsonError) throw new SyntaxError('not JSON');
            return r.body;
          }
        };
      }
    };
    vm.runInNewContext(input.expression, sandbox).then(result => {
      process.stdout.write(JSON.stringify(result));
    });
    """
    node = shutil.which("node")
    assert node is not None
    outcome = subprocess.run(
        [node, "-e", script],
        input=json.dumps({"response": response, "expression": expression}),
        text=True,
        capture_output=True,
        check=True,
        timeout=5,
    )
    assert json.loads(outcome.stdout) == {"state": expected}
    assert "SANITIZED" not in outcome.stdout  # identity stays inside the page


def test_liquidity_candidate_observes_existing_entry_without_fetch(setup):
    from dataclasses import replace

    from dogopencli.browser.environment import LIQUIDITY_STARTUP_URL

    env, transport = setup
    env = replace(env, startup_url=LIQUIDITY_STARTUP_URL)
    transport.targets[0]["url"] = LIQUIDITY_STARTUP_URL
    transport.result = {
        "origin": "https://iliquidity.alipay.com",
        "path": "/GUAPW3SG/menu/PortfolioMgmt",
        "ready_state": "complete",
        "document_id": 123,
    }
    candidate = probe_login_completion(env)
    assert candidate is not None
    assert transport.session.closed
    assert all("fetch(" not in expression for expression in transport.expressions)


def test_liquidity_old_entry_does_not_interrupt_pending_sso(setup):
    from dataclasses import replace

    from dogopencli.browser.environment import LIQUIDITY_STARTUP_URL

    env, transport = setup
    env = replace(env, startup_url=LIQUIDITY_STARTUP_URL)
    transport.targets[0]["url"] = LIQUIDITY_STARTUP_URL
    transport.targets.append(
        {
            "type": "page",
            "url": "https://tonelogin.antglobal-inc.com/mfa",
            "webSocketDebuggerUrl": "ws://fake/mfa",
        }
    )
    transport.result = {
        "origin": "https://iliquidity.alipay.com",
        "path": "/GUAPW3SG/menu/PortfolioMgmt",
        "ready_state": "complete",
        "document_id": 123,
    }
    with pytest.raises(AuthError) as caught:
        probe_login_completion(env)
    assert caught.value.code == "service_failure"
    assert transport.expressions == []


@pytest.mark.parametrize("document_id", [0, -1, True, float("inf"), float("nan"), None])
def test_liquidity_candidate_rejects_invalid_document_identity(setup, document_id):
    from dataclasses import replace

    from dogopencli.browser.environment import LIQUIDITY_STARTUP_URL

    env, transport = setup
    env = replace(env, startup_url=LIQUIDITY_STARTUP_URL)
    transport.targets[0]["url"] = LIQUIDITY_STARTUP_URL
    transport.result = {
        "origin": "https://iliquidity.alipay.com",
        "path": "/GUAPW3SG/menu/PortfolioMgmt",
        "ready_state": "complete",
        "document_id": document_id,
    }
    with pytest.raises(AuthError) as caught:
        probe_login_completion(env)
    assert caught.value.code == "service_failure"
    assert transport.session.closed


def test_liquidity_completed_other_tab_is_not_hidden_by_old_tab(setup, monkeypatch):
    from dataclasses import replace

    from dogopencli.browser.environment import LIQUIDITY_STARTUP_URL

    env, transport = setup
    env = replace(env, startup_url=LIQUIDITY_STARTUP_URL)
    transport.targets = [
        {
            "type": "page",
            "url": LIQUIDITY_STARTUP_URL,
            "webSocketDebuggerUrl": "ws://fake/old",
        },
        {
            "type": "page",
            "url": LIQUIDITY_STARTUP_URL,
            "webSocketDebuggerUrl": "ws://fake/completed",
        },
    ]
    sessions = []

    class DocumentSession(Session):
        def __init__(self, transport, ws_url):
            super().__init__(transport)
            self.ws_url = ws_url

        def evaluate(self, expression, timeout):
            return {
                "origin": "https://iliquidity.alipay.com",
                "path": "/GUAPW3SG/menu/PortfolioMgmt",
                "ready_state": "loading" if self.ws_url.endswith("old") else "complete",
                "document_id": 123,
            }

    def attach(ws_url, *, timeout):
        session = DocumentSession(transport, ws_url)
        sessions.append(session)
        return session

    monkeypatch.setattr(transport, "open_session", attach)
    candidate = probe_login_completion(env)
    assert candidate == ("ws://fake/completed", 123)
    assert len(sessions) == 2 and all(session.closed for session in sessions)
