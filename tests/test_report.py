import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

import pytest

from slo_toolkit.report import load_csv, report_from_csv, report_from_prometheus, report_from_rows
from slo_toolkit.simulate import simulate


@pytest.fixture(scope="module")
def demo_reports(tmp_path_factory):
    from slo_toolkit.spec import load_spec

    from .conftest import ROOT

    spec = load_spec(ROOT / "examples/http-api/checkout-api.slo.yaml")
    csv_path = tmp_path_factory.mktemp("data") / "samples.csv"
    simulate(spec, csv_path)
    return report_from_csv(spec, csv_path)


def test_simulated_scenario_pages_once_and_tickets_once(demo_reports):
    for report in demo_reports:
        severities = [e.severity for e in report.episodes]
        assert severities == ["page", "ticket"], report.episodes
        page = report.episodes[0]
        assert page.trigger.startswith("1h/5m")
        assert page.start.startswith("2026-09-14")  # the 40-minute outage, not the 4-minute blip on 09-07
        assert report.episodes[1].trigger.startswith("3d/6h")


def test_simulated_budget_is_partly_spent(demo_reports):
    for report in demo_reports:
        assert 0.3 < report.budget_remaining < 0.7
        assert report.status == "OK"


def test_simulation_is_deterministic(checkout, tmp_path):
    a, b = tmp_path / "a.csv", tmp_path / "b.csv"
    simulate(checkout, a, days=2)
    simulate(checkout, b, days=2)
    assert a.read_text() == b.read_text()


def _rows(error_ratio, n=60, total=1000):
    return [(i * 60, total * (1 - error_ratio), total) for i in range(n)]


def test_report_math(checkout):
    report = report_from_rows(checkout.slos[0], _rows(0.0005), "test")
    assert report.sli == pytest.approx(0.9995)
    assert report.budget_remaining == pytest.approx(0.5)
    assert report.burn_rates["1h"] == pytest.approx(0.5)
    assert report.episodes == []


def test_report_flags_missed_slo(checkout):
    report = report_from_rows(checkout.slos[0], _rows(0.05), "test")
    assert report.status == "SLO MISSED"
    assert report.episodes[0].severity == "page"
    assert report.episodes[0].end == "still firing"


def test_csv_missing_columns(tmp_path):
    path = tmp_path / "x.csv"
    path.write_text("timestamp,good,total\n1,1,1\n")
    with pytest.raises(ValueError, match="missing CSV columns: slo"):
        load_csv(path)


def test_csv_missing_slo(checkout, tmp_path):
    path = tmp_path / "x.csv"
    path.write_text("timestamp,slo,good,total\n0,availability,1,1\n")
    with pytest.raises(ValueError, match="no rows for SLO 'latency'"):
        report_from_csv(checkout, path)


class _FakeProm(BaseHTTPRequestHandler):
    """Answers every instant query with a 0.05% error ratio."""

    def do_GET(self):
        query = parse_qs(urlparse(self.path).query)["query"][0]
        value = "0.0005" if "http_requests_total" in query else "0.002"
        body = json.dumps(
            {"status": "success", "data": {"resultType": "vector", "result": [{"metric": {}, "value": [0, value]}]}}
        )
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body.encode())

    def log_message(self, *args):
        pass


def test_report_from_prometheus(checkout):
    server = HTTPServer(("127.0.0.1", 0), _FakeProm)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        reports = report_from_prometheus(checkout, f"http://127.0.0.1:{server.server_port}")
    finally:
        server.shutdown()
    availability, latency = reports
    assert availability.budget_remaining == pytest.approx(0.5)
    assert latency.budget_remaining == pytest.approx(0.8)  # 0.2% errors against a 1% budget
    assert availability.episodes == []
