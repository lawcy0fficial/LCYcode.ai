"""
compaction.py
Keeps session storage and prompt context bounded as a build runs long,
instead of growing without limit. Two separate things get compacted:

- the execution log persisted in a session's "pending" state, which
  can otherwise balloon with every write_file's full file content
  duplicated in both "args" and the diff "result" for every single
  iteration of a long auto-continue chain (up to max_total_iterations
  chunks per run)
- per-turn history text folded into the next DESCRIBE prompt, which
  otherwise grows in the length of any one turn's summary even though
  turn *count* was already capped

Older log entries are summarized down to their essential shape (tool,
path, ok/error) rather than dropped outright, so the story of what
happened stays legible even once detail is gone. Recent entries stay
full, since those are what execute.py/review.py actually look at
(completed_log[-10:]) when deciding the next tool call — keeping more
recent entries full than that window ever needs is deliberate
headroom, not waste.
"""

KEEP_RECENT_LOG_ENTRIES = 20
MAX_TEXT_LENGTH = 240


def compact_log(completed_log: list) -> list:
    """Returns a new list: the most recent KEEP_RECENT_LOG_ENTRIES
    entries unchanged, anything older reduced to a lightweight
    summary (tool, path, ok/error — no file content). Idempotent —
    an already-compacted entry is left as-is, so calling this
    repeatedly across many checkpoints doesn't re-process the same
    old entries every time."""
    if len(completed_log) <= KEEP_RECENT_LOG_ENTRIES:
        return completed_log

    cutoff = len(completed_log) - KEEP_RECENT_LOG_ENTRIES
    compacted = []
    for entry in completed_log[:cutoff]:
        if entry.get("_compacted"):
            compacted.append(entry)
            continue
        result = entry.get("result") or {}
        compacted.append({
            "step_id": entry.get("step_id"),
            "tool": entry.get("tool"),
            "path": (entry.get("args") or {}).get("path"),
            "ok": result.get("ok", True),
            "_compacted": True,
        })
    return compacted + completed_log[cutoff:]


def truncate(text: str, limit: int = MAX_TEXT_LENGTH) -> str:
    if not text:
        return text
    return text if len(text) <= limit else text[: limit].rstrip() + "…"
