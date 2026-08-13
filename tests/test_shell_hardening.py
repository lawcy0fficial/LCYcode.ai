import sys

from lcycode.tools.shell import run_shell
from lcycode.tools.shell_guard import apply_resource_limits


def test_run_shell_blocks_dangerous_command_without_executing_it():
    # if this actually ran, it would try to remove things — since it's
    # blocked, no subprocess is spawned at all
    result = run_shell("sudo rm -rf /")
    assert result["ok"] is False
    assert result["blocked"] is True
    assert "reason" in result
    assert "returncode" not in result  # never got as far as actually running


def test_run_shell_executes_a_normal_command_unaffected():
    result = run_shell("echo hello")
    assert result["ok"] is True
    assert "hello" in result["stdout"]
    assert "blocked" not in result


def test_run_shell_still_respects_timeout_for_allowed_commands():
    result = run_shell("sleep 5", timeout=1)
    assert result["ok"] is False
    assert "timed out" in result.get("error", "")


def test_apply_resource_limits_returns_none_on_windows(monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    assert apply_resource_limits() is None


def test_apply_resource_limits_returns_a_callable_on_posix(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    limiter = apply_resource_limits()
    assert callable(limiter)


def test_run_shell_actually_applies_a_memory_limit():
    """Not just that the function exists — that a command run through
    run_shell genuinely has a lowered RLIMIT_AS in its own process,
    proving preexec_fn is really wired in, not just defined."""
    result = run_shell(
        "python3 -c \"import resource; print(resource.getrlimit(resource.RLIMIT_AS)[0])\""
    )
    assert result["ok"] is True
    limit = int(result["stdout"].strip())
    assert limit == 1024 * 1024 * 1024  # the default_max_memory_mb=1024 from apply_resource_limits()
