"""The typer floor in pyproject.toml must be a typer the CLI actually runs on.

pyproject.toml declared `typer>=0.12`, but installing the built wheel with older typer
releases broke every command:
- typer 0.12.0 to 0.12.3 cannot read the `Path | None` options (RuntimeError: Type not yet
  supported), whatever the click version;
- typer 0.12.4 to 0.15.3 with click 8.2 or later (the version pip picks today) fail with
  "Secondary flag is not valid for non-boolean flag" (0.12.x, every command) or
  "make_metavar() missing 1 required positional argument: 'ctx'" (0.13 to 0.15.3, `--help`).
pip keeps an already-installed typer that meets the floor, so this hits anyone installing
slo-toolkit next to an older typer. typer 0.15.4 is the first release that runs the CLI and
caps click below 8.2 itself; 0.16.0 and later work with current click.
"""

import re
import tomllib

from .conftest import ROOT


def _floor(name: str) -> tuple[int, ...]:
    deps = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["dependencies"]
    for dep in deps:
        match = re.fullmatch(rf"{name}>=(\d+(?:\.\d+)*)", dep)
        if match:
            return tuple(int(part) for part in match.group(1).split("."))
    raise AssertionError(f"no '{name}>=' floor in {deps}")


def test_typer_floor_is_a_release_the_cli_runs_on():
    assert _floor("typer") >= (0, 15, 4)
