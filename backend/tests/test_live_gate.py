"""Live tests are skipped unless RUN_LIVE=1, whatever -m expression is given (tests/conftest.py)."""

from pathlib import Path

import pytest

pytest_plugins = ["pytester"]

CONFTEST = (Path(__file__).parent / "conftest.py").read_text(encoding="utf-8")
LIVE_FILE = """
import pytest

@pytest.mark.live
def test_contacts_network():
    pass

def test_offline():
    pass
"""


@pytest.fixture
def project(pytester):
    pytester.makeconftest(CONFTEST)
    pytester.makeini("[pytest]\nmarkers =\n    live: real sources\n    slow: slow\n")
    pytester.makepyfile(test_x=LIVE_FILE)
    return pytester


@pytest.mark.parametrize("args", [(), ("-m", "not slow"), ("-m", "live")])
def test_live_skipped_without_run_live(project, monkeypatch, args):
    monkeypatch.delenv("RUN_LIVE", raising=False)
    res = project.runpytest_inprocess(*args)
    outcomes = res.parseoutcomes()
    assert outcomes.get("skipped") == 1 and "failed" not in outcomes
    assert outcomes.get("passed", 0) == (0 if args == ("-m", "live") else 1)


def test_live_runs_with_run_live(project, monkeypatch):
    monkeypatch.setenv("RUN_LIVE", "1")
    res = project.runpytest_inprocess("-m", "live")
    res.assert_outcomes(passed=1, deselected=1)
