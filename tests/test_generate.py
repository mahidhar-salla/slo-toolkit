import json

import pytest
import yaml

from slo_toolkit.dashboard import dashboard, render_dashboard
from slo_toolkit.helm import render_values
from slo_toolkit.rules import alert_windows, render_rules, rule_groups
from slo_toolkit.spec import load_spec

from .conftest import EXAMPLES


def test_groups_per_slo(checkout):
    names = [g["name"] for g in rule_groups(checkout)["groups"]]
    assert names == ["slo-checkout-api-availability", "slo-checkout-api-latency"]


def test_recording_windows(checkout):
    slo = checkout.slos[0]
    assert alert_windows(slo) == ["5m", "30m", "1h", "2h", "6h", "1d", "3d"]
    records = [r["record"] for r in rule_groups(checkout)["groups"][0]["rules"] if "record" in r]
    for window in alert_windows(slo):
        assert f"slo:sli_error:ratio_rate{window}" in records
    assert "slo:error_budget_remaining:ratio" in records


def test_period_ratio_is_request_weighted(checkout):
    for group in rule_groups(checkout)["groups"]:
        rules = {r["record"]: r["expr"] for r in group["rules"] if "record" in r}
        assert "slo:sli_bad:rate5m" in rules and "slo:sli_total:rate5m" in rules
        period = rules["slo:period_error:ratio"]
        assert "avg_over_time" not in period
        assert "sum_over_time(slo:sli_bad:rate5m" in period and "sum_over_time(slo:sli_total:rate5m" in period
    availability, latency = (g["rules"] for g in rule_groups(checkout)["groups"])
    bad = {r["record"]: r["expr"] for r in availability if "record" in r}["slo:sli_bad:rate5m"]
    assert bad.endswith("or vector(0)")  # no 5xx series yet still reads as zero errors
    bad = {r["record"]: r["expr"] for r in latency if "record" in r}["slo:sli_bad:rate5m"]
    assert "\n-\n" in bad  # good-based SLI becomes total - good


def test_alerts_follow_workbook(checkout):
    alerts = [r for r in rule_groups(checkout)["groups"][0]["rules"] if "alert" in r]
    page, ticket = alerts
    assert page["labels"]["severity"] == "page"
    assert "ratio_rate1h" in page["expr"] and "ratio_rate5m" in page["expr"] and "(14.4 * 0.001)" in page["expr"]
    assert "ratio_rate6h" in page["expr"] and "ratio_rate30m" in page["expr"] and "(6 * 0.001)" in page["expr"]
    assert ticket["labels"]["severity"] == "ticket"
    assert "(3 * 0.001)" in ticket["expr"] and "(1 * 0.001)" in ticket["expr"]
    assert "for" not in page  # the short window does the debouncing, not a `for:` clause
    assert page["annotations"]["runbook_url"].endswith("error-budget-burn.md")


def test_custom_labels_and_table_profile():
    spec = load_spec(next(p for p in EXAMPLES if p.parent.name == "batch-job"))
    alerts = [r for r in rule_groups(spec)["groups"][0]["rules"] if "alert" in r]
    assert alerts[0]["labels"]["route"] == "team-channel"
    assert "ratio_rate1d" not in alerts[1]["expr"]  # workbook-table has no 1d/2h step


def test_rules_yaml_has_no_anchors(checkout):
    text = render_rules(checkout)
    assert "&id" not in text and "*id" not in text
    assert yaml.safe_load(text)["groups"]


def test_dashboard_shape(checkout):
    dash = dashboard(checkout)
    assert dash["uid"] == "slo-checkout-api"
    titles = [p["title"] for p in dash["panels"]]
    assert titles.count("Error budget remaining") == 4  # stat + timeseries per SLO
    ids = [p["id"] for p in dash["panels"]]
    assert len(ids) == len(set(ids))
    for panel in dash["panels"]:
        for target in panel.get("targets", []):
            assert 'slo_service="checkout-api"' in target["expr"]


def test_helm_values(checkout):
    values = yaml.safe_load(render_values(checkout))
    assert values["groups"] == rule_groups(checkout)["groups"]
    assert json.loads(values["dashboard"]["json"])["uid"] == "slo-checkout-api"


@pytest.mark.parametrize("path", EXAMPLES, ids=lambda p: p.parent.name)
def test_committed_example_outputs_are_current(path):
    """Golden files: examples/*/out must match what the generator produces today."""
    spec = load_spec(path)
    out = path.parent / "out"
    assert (out / f"{spec.service}.rules.yaml").read_text() == render_rules(spec), "run `make examples`"
    assert (out / f"{spec.service}.dashboard.json").read_text() == render_dashboard(spec), "run `make examples`"
