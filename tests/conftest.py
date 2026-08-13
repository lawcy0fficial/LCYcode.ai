"""
conftest.py
Runs before any test module in this directory is imported. Points
LCYCODE_WORKSPACE_ROOT at a fresh temp directory for the entire test
session, so every tool call, session file, and log line the suite
generates lands there instead of the real project's workspace/ — the
directory that actually ships. This must happen before `import lcycode`
occurs anywhere, which is why it's here rather than in a fixture.
"""
import atexit
import os
import shutil
import tempfile

_TEST_WORKSPACE = tempfile.mkdtemp(prefix="lcycode-test-workspace-")
os.environ["LCYCODE_WORKSPACE_ROOT"] = _TEST_WORKSPACE
atexit.register(shutil.rmtree, _TEST_WORKSPACE, ignore_errors=True)
