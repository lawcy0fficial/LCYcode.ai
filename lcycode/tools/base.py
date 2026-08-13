"""Sandboxing helpers shared by every tool."""
from lcycode.config.settings import WORKSPACE_ROOT


class ToolError(Exception):
    pass


def resolve(rel_path: str):
    p = (WORKSPACE_ROOT / rel_path).resolve()
    if WORKSPACE_ROOT not in p.parents and p != WORKSPACE_ROOT:
        raise ToolError(f"path escapes workspace: {rel_path}")
    return p
