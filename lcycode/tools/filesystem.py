"""Filesystem tools: write_file, read_file, edit_file, list_dir."""
from lcycode.config.settings import WORKSPACE_ROOT
from lcycode.tools.base import resolve, ToolError


def write_file(path: str, content: str) -> dict:
    p = resolve(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content)
    return {"ok": True, "path": str(p.relative_to(WORKSPACE_ROOT)), "bytes": len(content)}


def read_file(path: str) -> dict:
    p = resolve(path)
    if not p.exists():
        raise ToolError(f"no such file: {path}")
    return {"ok": True, "path": path, "content": p.read_text()}


def edit_file(path: str, find: str, replace: str) -> dict:
    p = resolve(path)
    if not p.exists():
        raise ToolError(f"no such file: {path}")
    text = p.read_text()
    if find not in text:
        raise ToolError(f"find-text not present in {path}")
    p.write_text(text.replace(find, replace, 1))
    return {"ok": True, "path": path}


def list_dir(path: str = ".") -> dict:
    p = resolve(path)
    if not p.exists():
        return {"ok": True, "entries": []}
    entries = sorted(f"{e.name}/" if e.is_dir() else e.name for e in p.iterdir())
    return {"ok": True, "path": path, "entries": entries}


def append_file(path: str, content: str) -> dict:
    p = resolve(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a") as f:
        f.write(content)
    return {"ok": True, "path": path, "appended_bytes": len(content)}


def delete_file(path: str) -> dict:
    p = resolve(path)
    if not p.exists():
        raise ToolError(f"no such file: {path}")
    if p.is_dir():
        raise ToolError(f"refusing to delete a directory with delete_file: {path}")
    p.unlink()
    return {"ok": True, "path": path, "deleted": True}
