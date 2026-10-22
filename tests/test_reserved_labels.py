"""Spec `labels` must not override the identity labels the generated rules select on.

Recording rules carry `slo_service`/`slo_name` (plus `slo_owner`, and `slo_window` on the
window-level series), and later rules select on those exact values. If a custom label could
override one of them, the derived series would silently select nothing.
"""

import pytest
import yaml

from slo_toolkit.rules import render_rules, rule_groups, series_labels
from slo_toolkit.spec import SpecError, load_spec

SPEC = """
apiVersion: slo-toolkit/v1
service: demo
owner: team-a
labels:
  {labels}
slos:
  - name: availability
    objective: 99.9
    window: 30d
    sli:
      bad: sum(rate(e[{{{{window}}}}]))
      total: sum(rate(t[{{{{window}}}}]))
"""


def spec_with(labels: str) -> str:
    return SPEC.format(labels=labels)


@pytest.mark.parametrize("reserved", ["slo_service", "slo_name", "slo_owner", "slo_window"])
def test_reserved_label_rejected(write_spec, reserved):
    with pytest.raises(SpecError, match=reserved):
        load_spec(write_spec(spec_with(f'{reserved}: "other"')))


def test_error_names_the_field(write_spec):
    with pytest.raises(SpecError, match="labels"):
        load_spec(write_spec(spec_with('slo_name: "other"')))


def test_ordinary_labels_preserved(write_spec):
    spec = load_spec(write_spec(spec_with('tier: "1"\n  team: payments')))
    slo = spec.slos[0]
    labels = series_labels(spec, slo)
    assert labels == {
        "slo_service": "demo",
        "slo_name": "availability",
        "slo_owner": "team-a",
        "tier": "1",
        "team": "payments",
    }


def test_every_recorded_series_keeps_its_identity(write_spec):
    """End to end: the rendered rules file keeps the identity labels the selectors use."""
    spec = load_spec(write_spec(spec_with('tier: "1"')))
    rendered = yaml.safe_load(render_rules(spec))
    assert rendered == rule_groups(spec)
    for group in rendered["groups"]:
        for rule in group["rules"]:
            assert rule["labels"]["slo_service"] == "demo"
            assert rule["labels"]["slo_name"] == "availability"
            assert rule["labels"].get("tier", "1") == "1"
