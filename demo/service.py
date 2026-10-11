"""A tiny synthetic service for the demo stack. Standard library only.

It doesn't serve real traffic; a background loop simulates ~RPS requests per second and
exposes Prometheus metrics at /metrics. Failure injection is a POST away:

    curl -XPOST 'localhost:8080/chaos?error_rate=0.2&latency_ms=600&seconds=600'
    curl -XPOST 'localhost:8080/chaos?reset=1'
"""

from __future__ import annotations

import json
import os
import random
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

RPS = float(os.environ.get("RPS", "40"))
BASE_ERROR_RATE = float(os.environ.get("BASE_ERROR_RATE", "0.0003"))
BUCKETS = (0.05, 0.1, 0.3, 0.5, 1.0, 2.5)

lock = threading.Lock()
requests = {"200": 0, "500": 0}
bucket_counts = dict.fromkeys(BUCKETS, 0)
duration_sum = 0.0
chaos = {"error_rate": 0.0, "latency_ms": 0.0, "until": 0.0}


def simulate_forever() -> None:
    global duration_sum
    rng = random.Random(42)
    while True:
        now = time.time()
        active = now < chaos["until"]
        error_rate = max(BASE_ERROR_RATE, chaos["error_rate"]) if active else BASE_ERROR_RATE
        extra = chaos["latency_ms"] / 1000 if active else 0.0
        with lock:
            for _ in range(int(RPS)):
                code = "500" if rng.random() < error_rate else "200"
                requests[code] += 1
                latency = rng.lognormvariate(-3.0, 0.6) + extra * rng.random()
                duration_sum += latency
                for le in BUCKETS:
                    if latency <= le:
                        bucket_counts[le] += 1
        time.sleep(max(0.0, 1 - (time.time() - now)))


def metrics() -> str:
    with lock:
        lines = [
            "# HELP http_requests_total Simulated HTTP requests.",
            "# TYPE http_requests_total counter",
            *(f'http_requests_total{{code="{code}"}} {n}' for code, n in requests.items()),
            "# HELP http_request_duration_seconds Simulated request latency.",
            "# TYPE http_request_duration_seconds histogram",
            *(f'http_request_duration_seconds_bucket{{le="{le}"}} {n}' for le, n in bucket_counts.items()),
            f'http_request_duration_seconds_bucket{{le="+Inf"}} {sum(requests.values())}',
            f"http_request_duration_seconds_sum {duration_sum:.3f}",
            f"http_request_duration_seconds_count {sum(requests.values())}",
        ]
    return "\n".join(lines) + "\n"


class Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, body: str, ctype: str = "application/json") -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.end_headers()
        self.wfile.write(body.encode())

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/metrics":
            self._send(200, metrics(), "text/plain; version=0.0.4")
        elif path == "/chaos":
            self._send(200, json.dumps(chaos))
        elif path in ("/", "/healthz"):
            self._send(200, '{"status": "ok"}')
        else:
            self._send(404, '{"error": "not found"}')

    def do_POST(self) -> None:
        url = urlparse(self.path)
        if url.path != "/chaos":
            self._send(404, '{"error": "not found"}')
            return
        q = {k: v[0] for k, v in parse_qs(url.query).items()}
        if q.get("reset"):
            chaos.update(error_rate=0.0, latency_ms=0.0, until=0.0)
        else:
            chaos.update(
                error_rate=float(q.get("error_rate", 0.2)),
                latency_ms=float(q.get("latency_ms", 0)),
                until=time.time() + float(q.get("seconds", 600)),
            )
        self._send(200, json.dumps(chaos))

    def log_message(self, *args: object) -> None:
        pass


if __name__ == "__main__":
    threading.Thread(target=simulate_forever, daemon=True).start()
    port = int(os.environ.get("PORT", "8080"))
    print(f"synthetic checkout-api on :{port} (RPS={RPS}, base error rate={BASE_ERROR_RATE})", flush=True)
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()
