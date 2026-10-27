"""Label names in a spec must be ones Prometheus will load.

Prometheus reserves label names that begin with `__` for internal use, and a label name
can't be empty. Before this check, `validate` and `generate` accepted `__name__` or `""` in
spec `labels`, `page_labels` or `ticket_labels` and wrote rules that the pinned promtool
(3.5.0) rejects with "invalid label name", so the whole rule group would fail to load.
Other names, including UTF-8 names that Prometheus 3 accepts, are left alone.
"""

import pytest

from slo_toolkit.rules import alerting_rules, series_labels
from slo_toolkit.spec import SpecError, load_spec

SPEC = """
apiVersion: slo-toolkit/v1
service: demo
labels: {labels}
slos:
  - name: availability
    objective: 99.9
    window: 30d
    sli:
      bad: sum(rate(e[{{{{window}}}}]))
      total: sum(rate(t[{{{{window}}}}]))
    alerting:
      page_labels: {page}
      ticket_labels: {ticket}
"""


def spec_with(labels: str = "{}", page: str = "{severity: page}", ticket: str = "{severity: ticket}") -> str:
    return SPEC.format(labels=labels, page=page, ticket=ticket)


BAD_NAMES = ['""', "__name__", "__tenant"]


@pytest.mark.parametrize("name", BAD_NAMES)
def test_spec_label_name_rejected(write_spec, name):
    with pytest.raises(SpecError, match=r"labels: .*label name"):
        load_spec(write_spec(spec_with(labels=f"{{{name}: x}}")))


@pytest.mark.parametrize("name", BAD_NAMES)
@pytest.mark.parametrize("field", ["page", "ticket"])
def test_alert_label_name_rejected(write_spec, name, field):
    labels = {field: f"{{severity: {field}, {name}: x}}"}
    with pytest.raises(SpecError, match=rf"{field}_labels: .*label name"):
        load_spec(write_spec(spec_with(**labels)))


def test_ordinary_and_utf8_label_names_preserved(write_spec):
    spec = load_spec(
        write_spec(
            spec_with(
                labels='{tier: "1", team-name: payments, _private: y}',
                page="{severity: page, pager-team: sre}",
            )
        )
    )
    slo = spec.slos[0]
    assert series_labels(spec, slo) == {
        "slo_service": "demo",
        "slo_name": "availability",
        "tier": "1",
        "team-name": "payments",
        "_private": "y",
    }
    page = next(r for r in alerting_rules(spec, slo) if r["labels"]["severity"] == "page")
    assert page["labels"]["pager-team"] == "sre"
