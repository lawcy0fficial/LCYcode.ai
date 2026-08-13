"""
sessions.py
GET /api/session/{id} (in session.py, unchanged) reads one session by
a known id. This endpoint lists ALL of them — the discovery half of
that: without it, a client had no way to find a session it didn't
already have the id for (e.g. after clearing localStorage, or from a
second device). Reads directly off disk, same source of truth as
Session itself.
"""
import json

from fastapi import APIRouter

from lcycode.core.session import SESSIONS_DIR
from lcycode.core import run_registry

router = APIRouter()


@router.get("/api/sessions")
async def list_sessions():
    running = run_registry.status()
    seen = set()
    out = []
    for path in sorted(SESSIONS_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            data = json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        session_id = data.get("session_id", path.stem)
        seen.add(session_id)
        turns = data.get("turns", [])
        out.append({
            "session_id": session_id,
            "created_at": data.get("created_at"),
            "turn_count": len(turns),
            "last_summary": turns[-1]["summary"] if turns else None,
            "has_pending": data.get("pending") is not None,
            "currently_running": session_id in running,
        })

    # A session running its very first chunk hasn't checkpointed to
    # disk yet (Session only writes on set_pending/add_turn), so it
    # wouldn't otherwise show up here even though it's genuinely
    # in-flight — synthesize a minimal entry from run_registry so
    # "currently_running" is trustworthy immediately, not just after
    # the first checkpoint.
    for session_id in running:
        if session_id not in seen:
            out.insert(0, {
                "session_id": session_id, "created_at": None, "turn_count": 0,
                "last_summary": None, "has_pending": False, "currently_running": True,
            })

    return {"sessions": out}
