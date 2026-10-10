from pathlib import Path

import pytest

from app.data.base import SourceError
from app.data.execution import ExecutionClient, HttpJsonLoader


def test_execution_shim_reports_not_mapped_and_points_to_mf_client():
    """app.data.execution is only an import-compatible shim until refresh is rewired (Task 4):
    the real source is app.data.mf_execution.MfBudgetExecutionClient."""
    with pytest.raises(SourceError, match="not mapped") as e:
        ExecutionClient(HttpJsonLoader()).fetch()
    assert e.value.source == "execution"
    assert "mf_execution" in e.value.message


def test_execution_shim_has_no_placeholder_endpoints():
    import app.data.execution as execution
    import app.data.series_map as series_map

    assert not hasattr(series_map, "EXECUTION_ENDPOINTS")
    assert not hasattr(execution, "EXECUTION_ENDPOINTS")
    assert "TODO_VERIFY" not in Path(execution.__file__).read_text(encoding="utf-8")
    assert "TODO_VERIFY" not in Path(series_map.__file__).read_text(encoding="utf-8")
