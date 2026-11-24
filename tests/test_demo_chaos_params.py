"""The demo service's /chaos endpoint answers a bad parameter with 400, not a dropped connection.

`POST /chaos?error_rate=abc` raised ValueError inside the handler: the client got an empty
reply and the server printed a traceback. `nan` and `inf` were accepted: `latency_ms=nan`
turned `http_request_duration_seconds_sum` into NaN for the life of the process (reset
did not clear it) and the reply held `NaN`/`Infinity`, which is not valid JSON. Each
value must now be a finite number; otherwise the reply is 400 and the chaos state is
left as it was.
"""

import importlib.util
import json
import threading
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer

import pytest

from .conftest import ROOT


@pytest.fixture
def demo():
    spec = importlib.util.spec_from_file_location("demo_service", ROOT / "demo/service.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    server = ThreadingHTTPServer(("127.0.0.1", 0), mod.Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield mod, server.server_address[1]
    server.shutdown()
    server.server_close()


def _post(port, query):
    conn = HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        conn.request("POST", f"/chaos?{query}")
        resp = conn.getresponse()
        return resp.status, resp.read().decode()
    finally:
        conn.close()


@pytest.mark.parametrize(
    "query",
    [
        "error_rate=abc",
        "latency_ms=fast",
        "seconds=x",
        "error_rate=nan",
        "latency_ms=nan",
        "seconds=nan",
        "seconds=inf",
        "latency_ms=-inf",
    ],
)
def test_bad_chaos_value_is_rejected(demo, query):
    mod, port = demo
    before = dict(mod.chaos)
    status, body = _post(port, query)
    assert status == 400, body
    assert query.split("=")[0] in json.loads(body)["error"]
    assert mod.chaos == before


def test_valid_chaos_and_reset_still_work(demo):
    mod, port = demo
    status, body = _post(port, "error_rate=0.2&latency_ms=600&seconds=60")
    assert status == 200
    state = json.loads(body, parse_constant=lambda c: pytest.fail(f"non-standard JSON {c}"))
    assert state["error_rate"] == 0.2 and state["latency_ms"] == 600.0
    assert mod.chaos == state
    status, body = _post(port, "reset=1")
    assert status == 200
    assert json.loads(body) == {"error_rate": 0.0, "latency_ms": 0.0, "until": 0.0}
