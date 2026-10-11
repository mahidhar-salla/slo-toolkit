from pathlib import Path

import pytest

from slo_toolkit.spec import Spec, load_spec

ROOT = Path(__file__).resolve().parent.parent
EXAMPLES = sorted((ROOT / "examples").glob("*/*.slo.yaml"))


@pytest.fixture
def checkout() -> Spec:
    return load_spec(ROOT / "examples/http-api/checkout-api.slo.yaml")


@pytest.fixture
def write_spec(tmp_path):
    def _write(text: str) -> Path:
        path = tmp_path / "x.slo.yaml"
        path.write_text(text)
        return path

    return _write
