import pytest

from slo_toolkit.spec import SpecError, load_spec, warnings_for

from .conftest import EXAMPLES

BASE = """
apiVersion: slo-toolkit/v1
service: demo
slos:
  - name: availability
    objective: {objective}
    window: {window}
    sli:
      {sli}
"""
OK_SLI = "bad: sum(rate(e[{{window}}]))\n      total: sum(rate(t[{{window}}]))"


def spec_text(objective="99.9", window="30d", sli=OK_SLI):
    return BASE.format(objective=objective, window=window, sli=sli)


@pytest.mark.parametrize("path", EXAMPLES, ids=lambda p: p.parent.name)
def test_examples_load(path):
    spec = load_spec(path)
    assert spec.slos


def test_good_and_bad_are_exclusive(write_spec):
    sli = "good: g[{{window}}]\n      bad: b[{{window}}]\n      total: t[{{window}}]"
    with pytest.raises(SpecError, match="exactly one"):
        load_spec(write_spec(spec_text(sli=sli)))


def test_window_placeholder_required(write_spec):
    with pytest.raises(SpecError, match="window"):
        load_spec(write_spec(spec_text(sli="bad: b[5m]\n      total: t[5m]")))


@pytest.mark.parametrize("objective", ["100", "0", "101"])
def test_objective_range(write_spec, objective):
    with pytest.raises(SpecError, match="objective"):
        load_spec(write_spec(spec_text(objective=objective)))


def test_short_window_rejected(write_spec):
    with pytest.raises(SpecError, match="at least 1d"):
        load_spec(write_spec(spec_text(window="6h")))


def test_unknown_field_rejected(write_spec):
    with pytest.raises(SpecError, match="Extra inputs"):
        load_spec(write_spec(spec_text() + "    owner_team: x\n"))


def test_duplicate_names(write_spec):
    text = spec_text() + "  - name: availability\n    objective: 99\n    sli:\n      " + OK_SLI + "\n"
    with pytest.raises(SpecError, match="duplicate"):
        load_spec(write_spec(text))


def test_missing_file(tmp_path):
    with pytest.raises(SpecError, match="not found"):
        load_spec(tmp_path / "nope.yaml")


def test_invalid_yaml(write_spec):
    with pytest.raises(SpecError, match="invalid YAML"):
        load_spec(write_spec("slos: [unclosed"))


def test_error_ratio_expr_good_form(checkout):
    expr = checkout.slos[1].sli.error_ratio_expr("1h")
    assert expr.startswith("1 - (")
    assert "[1h]" in expr and "{{window}}" not in expr


def test_warnings_for_low_objective(write_spec):
    # Workbook: at 90%, a full outage can't reach a 14.4x burn in 1h.
    spec = load_spec(write_spec(spec_text(objective="90")))
    assert any("can never fire" in w for w in warnings_for(spec))


def test_warnings_for_extreme_objective(write_spec):
    spec = load_spec(write_spec(spec_text(objective="99.99")))
    assert any("canaries" in w for w in warnings_for(spec))


def test_no_warnings_for_examples(checkout):
    assert warnings_for(checkout) == []
