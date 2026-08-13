"""
registry.py
Central registry the agent loop dispatches tool calls through, plus
TOOL_SCHEMA — the OpenAI-compatible function-calling schema for every
tool, used by providers that support native tool use (OpenRouter,
DeepSeek, Grok, and recent Ollama builds).

execute() is async and runs the actual tool call via asyncio.to_thread
— tool functions themselves stay plain synchronous Python (simpler to
write and test), but a slow one (run_shell, run_tests with a 180s
timeout) doesn't block the whole event loop while it runs. That
matters concretely for the WebSocket/SSE server: without this, a long
shell command in one session's run would freeze every other
connection on the server, including a client trying to cancel a
*different* run — a real bug, not a hypothetical one, caught while
building the cancellation feature.
"""
import asyncio

from lcycode.tools.base import ToolError
from lcycode.tools.filesystem import write_file, read_file, edit_file, list_dir, append_file, delete_file
from lcycode.tools.shell import run_shell
from lcycode.tools.search import search_files
from lcycode.tools.git import git_init, git_status, git_diff, git_commit, git_log
from lcycode.tools.quality import run_tests, run_lint

TOOL_SPECS = {
    "write_file": write_file,
    "read_file": read_file,
    "edit_file": edit_file,
    "append_file": append_file,
    "delete_file": delete_file,
    "list_dir": list_dir,
    "run_shell": run_shell,
    "search_files": search_files,
    "git_init": git_init,
    "git_status": git_status,
    "git_diff": git_diff,
    "git_commit": git_commit,
    "git_log": git_log,
    "run_tests": run_tests,
    "run_lint": run_lint,
}

FILE_MUTATING_TOOLS = {"write_file", "edit_file", "append_file", "delete_file"}


async def execute(tool_name: str, args: dict) -> dict:
    fn = TOOL_SPECS.get(tool_name)
    if not fn:
        raise ToolError(f"unknown tool: {tool_name}")

    # For anything that mutates a file's content, capture before/after
    # so callers (the GUI's live coding view) can render a real diff
    # instead of just the final file — the before-snapshot has to be
    # taken pre-execution, obviously, since the tool overwrites it.
    # These reads are fast/local, not worth their own thread hop.
    path = args.get("path")
    before = None
    if tool_name in FILE_MUTATING_TOOLS and path:
        try:
            before = read_file(path)["content"]
        except ToolError:
            before = None  # new file — nothing to diff against, that's fine

    result = await asyncio.to_thread(fn, **args)

    if tool_name in FILE_MUTATING_TOOLS and path:
        after = None
        if tool_name != "delete_file":
            try:
                after = read_file(path)["content"]
            except ToolError:
                after = None
        result = dict(result)
        result["diff"] = {"before": before, "after": after}

    return result


def _param(props, required):
    return {"type": "object", "properties": props, "required": required}


TOOL_SCHEMA = [
    {"type": "function", "function": {
        "name": "write_file", "description": "Create or overwrite a file with the given content.",
        "parameters": _param({"path": {"type": "string"}, "content": {"type": "string"}}, ["path", "content"])}},
    {"type": "function", "function": {
        "name": "read_file", "description": "Read a file's full contents.",
        "parameters": _param({"path": {"type": "string"}}, ["path"])}},
    {"type": "function", "function": {
        "name": "edit_file", "description": "Replace the first occurrence of `find` with `replace` in a file.",
        "parameters": _param({"path": {"type": "string"}, "find": {"type": "string"},
                               "replace": {"type": "string"}}, ["path", "find", "replace"])}},
    {"type": "function", "function": {
        "name": "append_file", "description": "Append content to the end of a file.",
        "parameters": _param({"path": {"type": "string"}, "content": {"type": "string"}}, ["path", "content"])}},
    {"type": "function", "function": {
        "name": "delete_file", "description": "Delete a single file (not a directory).",
        "parameters": _param({"path": {"type": "string"}}, ["path"])}},
    {"type": "function", "function": {
        "name": "list_dir", "description": "List entries in a workspace directory.",
        "parameters": _param({"path": {"type": "string"}}, [])}},
    {"type": "function", "function": {
        "name": "run_shell", "description": "Run a shell command inside the workspace sandbox. "
                "Commands that try to escape the workspace or perform destructive system operations "
                "(e.g. cd to an absolute path, rm -rf on a root/home path, sudo) are blocked and "
                "return {\"blocked\": true, \"reason\": ...} without executing.",
        "parameters": _param({"command": {"type": "string"},
                               "timeout": {"type": "integer"}}, ["command"])}},
    {"type": "function", "function": {
        "name": "search_files", "description": "Grep-like search for a string or regex across the workspace.",
        "parameters": _param({"pattern": {"type": "string"}, "path": {"type": "string"},
                               "regex": {"type": "boolean"}}, ["pattern"])}},
    {"type": "function", "function": {
        "name": "git_init", "description": "Initialize a git repo in the workspace if one doesn't exist.",
        "parameters": _param({}, [])}},
    {"type": "function", "function": {
        "name": "git_status", "description": "Show working-tree status (git status --porcelain).",
        "parameters": _param({}, [])}},
    {"type": "function", "function": {
        "name": "git_diff", "description": "Show unstaged changes, optionally scoped to one path.",
        "parameters": _param({"path": {"type": "string"}}, [])}},
    {"type": "function", "function": {
        "name": "git_commit", "description": "Stage everything and commit with the given message.",
        "parameters": _param({"message": {"type": "string"}}, ["message"])}},
    {"type": "function", "function": {
        "name": "git_log", "description": "Show recent commits, one line each.",
        "parameters": _param({"limit": {"type": "integer"}}, [])}},
    {"type": "function", "function": {
        "name": "run_tests", "description": "Run the workspace's test suite (auto-detects pytest/npm).",
        "parameters": _param({}, [])}},
    {"type": "function", "function": {
        "name": "run_lint", "description": "Run the workspace's linter (auto-detects ruff/flake8/eslint).",
        "parameters": _param({}, [])}},
]
