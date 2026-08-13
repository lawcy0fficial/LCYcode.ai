"""run_shell — executes a command inside the workspace sandbox with a
timeout, a pattern-based guard against obviously destructive commands,
and best-effort resource limits. See shell_guard.py for exactly what
this is and isn't — it's defense-in-depth, not a real sandbox."""
import subprocess

from lcycode.config.settings import WORKSPACE_ROOT
from lcycode.tools.shell_guard import check_command, apply_resource_limits


def run_shell(command: str, timeout: int = 60) -> dict:
    block_reason = check_command(command)
    if block_reason:
        return {"ok": False, "blocked": True, "reason": block_reason,
                "error": f"command blocked: {block_reason}"}

    try:
        result = subprocess.run(
            command,
            shell=True,
            cwd=WORKSPACE_ROOT,
            capture_output=True,
            text=True,
            timeout=timeout,
            preexec_fn=apply_resource_limits(),
        )
        return {
            "ok": result.returncode == 0,
            "returncode": result.returncode,
            "stdout": result.stdout[-4000:],
            "stderr": result.stderr[-4000:],
        }
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": f"command timed out after {timeout}s"}
