"""
session.py
Lightweight persisted session store so a chat "session_id" can span
multiple /api/chat calls: prior task descriptions and execution
history are folded into the next run's context instead of starting
from a blank slate every message.

Sessions are stored as plain JSON files under workspace/.lcycode/sessions/
so the CLI and GUI both see the same state, and a restart doesn't lose
anything.

Both storage vectors that could otherwise grow without bound are
compacted (see compaction.py): the execution log kept in "pending"
state gets old entries summarized down once it's long, and per-turn
text gets truncated before being stored — the *number* of turns was
already capped, but nothing previously bounded how long any single
turn's text could be.
"""
import json
import time
import uuid
from pathlib import Path

from lcycode.config.settings import WORKSPACE_ROOT
from lcycode.core.compaction import compact_log, truncate

SESSIONS_DIR = WORKSPACE_ROOT / ".lcycode" / "sessions"
SESSIONS_DIR.mkdir(parents=True, exist_ok=True)

MAX_HISTORY_TURNS = 12  # keep the session file bounded


class Session:
    def __init__(self, session_id: str):
        self.session_id = session_id
        self.path = SESSIONS_DIR / f"{session_id}.json"
        self.data = self._load()

    def _load(self):
        if self.path.exists():
            return json.loads(self.path.read_text())
        return {"session_id": self.session_id, "created_at": time.time(), "turns": [], "pending": None}

    def save(self):
        self.path.write_text(json.dumps(self.data, indent=2))

    def set_pending(self, user_task, description, steps, completed_log):
        """Stashes an unfinished run's state so continue_run() can pick
        it back up without repeating DESCRIBE/PLAN. completed_log is
        compacted here — the single point where pending state is
        persisted — rather than during the run itself, so the live
        in-memory log a run is actively working with stays untouched
        and full detail; only what actually hits disk gets bounded."""
        self.data["pending"] = {
            "user_task": user_task,
            "description": description,
            "steps": steps,
            "log": compact_log(completed_log),
            "iterations": len(completed_log),
        }
        self.save()

    def clear_pending(self):
        self.data["pending"] = None
        self.save()

    @property
    def has_pending(self) -> bool:
        return self.data.get("pending") is not None

    def add_turn(self, user_task: str, result: dict):
        self.data["turns"].append({
            "at": time.time(),
            "user_task": truncate(user_task),
            "summary": truncate((result.get("description") or {}).get("summary", "")),
            "iterations": result.get("iterations", 0),
        })
        self.data["turns"] = self.data["turns"][-MAX_HISTORY_TURNS:]
        self.save()

    def history_context(self) -> str:
        """A compact summary of prior turns to prepend to the next
        DESCRIBE stage, so the agent has continuity within a session."""
        if not self.data["turns"]:
            return ""
        lines = [
            f'- "{t["user_task"]}" -> {t["summary"]}' for t in self.data["turns"]
        ]
        return "Prior turns in this session:\n" + "\n".join(lines)


def get_or_create(session_id: str = None) -> Session:
    return Session(session_id or str(uuid.uuid4()))
