"""
settings.py
Single source of truth for filesystem paths used across the package,
so nothing hardcodes "../key.json"-style relative paths.

WORKSPACE_ROOT can be overridden via the LCYCODE_WORKSPACE_ROOT env
var — this is what tests/conftest.py uses to point every tool call,
session file, and log at an isolated temp directory instead of the
real project's workspace/, so running the test suite never leaves
test fixtures sitting in what actually ships.
"""
import os
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parent.parent   # .../lcycode
PROJECT_ROOT = PACKAGE_ROOT.parent                        # .../LCYcode.ai

KEY_FILE = PROJECT_ROOT / "key.json"
DEMO_KEY_FILE = PROJECT_ROOT / "key.demo.json"
WORKSPACE_ROOT = Path(os.environ.get("LCYCODE_WORKSPACE_ROOT", str(PROJECT_ROOT / "workspace")))
FRONTEND_DIR = PROJECT_ROOT / "frontend"

DEFAULT_ROUTING = {
    "order": ["ollama", "openrouter", "deepseek", "grok"],
    "max_iterations": 40,
    "tool_timeout_seconds": 60,
}

WORKSPACE_ROOT.mkdir(parents=True, exist_ok=True)
