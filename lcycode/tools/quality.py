"""Quality tools — run the workspace's own test suite / linter.
Auto-detects common Python and Node setups rather than assuming one."""
from pathlib import Path

from lcycode.config.settings import WORKSPACE_ROOT
from lcycode.tools.shell import run_shell


def run_tests() -> dict:
    if (WORKSPACE_ROOT / "pytest.ini").exists() or (WORKSPACE_ROOT / "tests").exists() \
            or any(WORKSPACE_ROOT.glob("test_*.py")):
        return run_shell("pytest -q 2>&1 || true", timeout=180)
    if (WORKSPACE_ROOT / "package.json").exists():
        return run_shell("npm test --silent 2>&1 || true", timeout=180)
    return {"ok": False, "error": "no recognizable test setup (pytest or package.json) found"}


def run_lint() -> dict:
    if any(WORKSPACE_ROOT.glob("*.py")) or (WORKSPACE_ROOT / "pyproject.toml").exists():
        return run_shell(
            "ruff check . 2>&1 || flake8 . 2>&1 || echo 'no python linter installed'",
            timeout=120,
        )
    if (WORKSPACE_ROOT / "package.json").exists():
        return run_shell("npx eslint . 2>&1 || echo 'no js linter installed'", timeout=120)
    return {"ok": False, "error": "no recognizable lint setup found"}
