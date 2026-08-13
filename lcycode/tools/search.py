"""search_files — grep-like text search confined to the workspace."""
import re

from lcycode.config.settings import WORKSPACE_ROOT
from lcycode.tools.base import resolve

MAX_MATCHES = 200
SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", ".lcycode"}


def search_files(pattern: str, path: str = ".", regex: bool = False) -> dict:
    root = resolve(path)
    matches = []
    matcher = re.compile(pattern) if regex else None

    for file_path in root.rglob("*"):
        if any(part in SKIP_DIRS for part in file_path.parts):
            continue
        if not file_path.is_file():
            continue
        try:
            text = file_path.read_text(errors="ignore")
        except OSError:
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            hit = matcher.search(line) if regex else (pattern in line)
            if hit:
                matches.append({
                    "path": str(file_path.relative_to(WORKSPACE_ROOT)),
                    "line": lineno,
                    "text": line.strip()[:200],
                })
                if len(matches) >= MAX_MATCHES:
                    return {"ok": True, "matches": matches, "truncated": True}

    return {"ok": True, "matches": matches, "truncated": False}
