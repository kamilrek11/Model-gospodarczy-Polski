"""Import-compatible shim for the former placeholder budget-execution client.

The real source is app.data.mf_execution.MfBudgetExecutionClient (MF reports, dane.gov.pl
dataset 163). refresh.get_clients still constructs ExecutionClient(HttpJsonLoader()) until it is
rewired (Task 4 of the real-data-sources plan); until then this source reports "not mapped".
"""

import pandas as pd

from app.data.base import SourceError

SOURCE = "execution"


class HttpJsonLoader:
    """Kept only so existing imports keep working; it loads nothing."""

    def __init__(self, *args, **kwargs):
        pass


class ExecutionClient:
    name = SOURCE

    def __init__(self, loader: HttpJsonLoader | None = None, *args, **kwargs):
        self.loader = loader

    def fetch(self) -> dict[str, pd.DataFrame]:
        raise SourceError(
            SOURCE,
            "series not mapped: budget execution comes from app.data.mf_execution."
            "MfBudgetExecutionClient (not wired into refresh yet)",
        )
