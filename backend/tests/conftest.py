"""Tests marked `live` contact the real public sources; they are skipped unless RUN_LIVE=1.

The skip does not depend on the -m expression (a user's `-m "not slow"` must never hit the network):
run them with `RUN_LIVE=1 pytest -m live`.
"""

import os

import pytest

RUN_LIVE_ENV = "RUN_LIVE"


def pytest_collection_modifyitems(config, items):
    if os.environ.get(RUN_LIVE_ENV, "").strip() == "1":
        return
    skip = pytest.mark.skip(reason=f"live test (real sources over the network): set {RUN_LIVE_ENV}=1 to run")
    for item in items:
        if item.get_closest_marker("live") is not None:
            item.add_marker(skip)
