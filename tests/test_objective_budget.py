"""An objective must leave a non-zero error budget.

`error_budget` rounds 1 - objective/100 to 10 decimal places, so an objective such as
99.99999999999 passed the 0 < objective < 100 check but got a budget of exactly 0. `validate`
and `generate` then exited 0 and wrote rules that divide by zero
(`slo:error_budget_remaining:ratio` is `1 - (... / 0)`) and alert on any error at all
(thresholds `14.4 * 0`), and `report` crashed with ZeroDivisionError. The smallest budget the
rounding can represent, 1e-10 (objective 99.99999999), keeps working.
"""

import pytest

from slo_toolkit.budget import error_budget
from slo_toolkit.rules import recording_rules
from slo_toolkit.spec import SpecError, load_spec

from .test_spec import spec_text

ZERO_BUDGET = ["99.99999999999", "99.999999996"]


@pytest.mark.parametrize("objective", [float(o) for o in ZERO_BUDGET])
def test_error_budget_never_returns_zero(objective):
    with pytest.raises(ValueError, match="error budget"):
        error_budget(objective)


@pytest.mark.parametrize("objective", ZERO_BUDGET)
def test_spec_rejects_objective_with_zero_budget(write_spec, objective):
    with pytest.raises(SpecError, match=r"objective: .*error budget"):
        load_spec(write_spec(spec_text(objective=objective)))


def test_smallest_representable_budget_still_works(write_spec):
    spec = load_spec(write_spec(spec_text(objective="99.99999999")))
    slo = spec.slos[0]
    assert slo.budget == pytest.approx(1e-10)
    remaining = next(r for r in recording_rules(spec, slo) if r["record"] == "slo:error_budget_remaining:ratio")
    assert remaining["expr"].endswith("/ 1e-10)")


@pytest.mark.parametrize("objective", [99.9, 99.0, 50.0, 0.001])
def test_ordinary_objectives_unchanged(objective):
    assert error_budget(objective) == pytest.approx(1 - objective / 100)
