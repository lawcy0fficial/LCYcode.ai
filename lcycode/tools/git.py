"""Git tools — thin, purpose-built wrappers instead of raw run_shell,
so the model has clear, low-risk verbs for version control."""
import shlex

from lcycode.tools.shell import run_shell


def git_init() -> dict:
    return run_shell("git init -q 2>&1 || true; git rev-parse --is-inside-work-tree")


def git_status() -> dict:
    return run_shell("git status --porcelain=v1")


def git_diff(path: str = "") -> dict:
    return run_shell(f"git diff -- {path}" if path else "git diff")


def git_commit(message: str) -> dict:
    quoted = shlex.quote(message)
    return run_shell(f"git add -A && git commit -q -m {quoted} || echo 'nothing to commit'")


def git_log(limit: int = 10) -> dict:
    return run_shell(f"git log --oneline -n {limit}")
