"""I-4: backend dependencies are pinned; test-only tools stay out of the runtime image."""

import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def project() -> dict:
    return tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]


def test_runtime_dependencies_are_exact_pins_without_test_tools():
    deps = project()["dependencies"]
    assert deps and all(re.fullmatch(r"[A-Za-z0-9_.\-\[\]]+==[0-9][0-9A-Za-z.]*", d) for d in deps), deps
    names = {d.split("==")[0].lower() for d in deps}
    assert {"fastapi", "uvicorn", "pandas", "numpy", "statsmodels", "httpx", "openpyxl"} <= names
    assert "pytest" not in names


def test_dev_group_pins_pytest():
    dev = project()["optional-dependencies"]["dev"]
    assert any(d.startswith("pytest==") for d in dev), dev


def test_dockerfile_installs_runtime_dependencies_only_and_documents_single_worker():
    text = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "['project']['dependencies']" in text and "optional-dependencies" not in text
    assert "single worker" in text.lower()
    assert "--workers" not in text or "--workers\", \"1\"" in text


def test_compose_passes_refresh_disabled_through_and_readme_warns():
    compose = (ROOT.parent / "docker-compose.yml").read_text(encoding="utf-8")
    assert 'REFRESH_DISABLED: "${REFRESH_DISABLED:-0}"' in compose
    readme = (ROOT.parent / "README.md").read_text(encoding="utf-8")
    assert "bez uwierzytelniania" in readme and "REFRESH_DISABLED=1 docker compose up" in readme
