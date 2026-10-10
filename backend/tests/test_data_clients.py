import importlib
from pathlib import Path

import pytest


def test_execution_placeholder_module_is_gone():
    """The budget-execution placeholder (app.data.execution) was replaced by app.data.mf_execution,
    which refresh.get_clients now wires in."""
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("app.data.execution")


def test_series_map_has_no_placeholder_endpoints():
    import app.data.series_map as series_map

    assert not hasattr(series_map, "EXECUTION_ENDPOINTS")
    assert "TODO_VERIFY" not in Path(series_map.__file__).read_text(encoding="utf-8")
