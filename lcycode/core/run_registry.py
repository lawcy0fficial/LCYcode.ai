"""
run_registry.py
Tracks in-flight AgentLoop runs, keyed by session_id, so a run started
by one request (an SSE POST or a WebSocket message) can be cancelled
by a *different* request — this is the actual point of it: SSE and a
plain POST are one-way, so without a shared registry there'd be no
way to reach a run once it's started except killing the process.

A cancellation is cooperative: AgentLoop checks the event between
stages and between EXECUTE/REVIEW iterations, and stops cleanly at
the next checkpoint rather than being killed mid-tool-call. A tool
call already in flight (e.g. a slow run_shell) still finishes; the
loop just doesn't start another one.
"""
import asyncio
import time

_registry: dict[str, dict] = {}


def register(session_id: str) -> asyncio.Event:
    """Called when a run starts. Returns the cancel_event AgentLoop
    should check; overwrites any stale entry for the same session
    (a session can only run one loop at a time)."""
    event = asyncio.Event()
    _registry[session_id] = {"cancel_event": event, "started_at": time.time()}
    return event


def unregister(session_id: str):
    """Called when a run finishes (complete, paused, or cancelled).
    Safe to call even if the session was never registered."""
    _registry.pop(session_id, None)


def request_cancel(session_id: str) -> bool:
    """Returns True if a run was actually found and signaled, False if
    there was nothing in-flight for that session (not an error — the
    caller may be cancelling a run that already finished)."""
    entry = _registry.get(session_id)
    if not entry:
        return False
    entry["cancel_event"].set()
    return True


def is_running(session_id: str) -> bool:
    return session_id in _registry


def status():
    """For the health/debug endpoint — which sessions are currently running."""
    now = time.time()
    return {
        sid: {"running_for_seconds": round(now - entry["started_at"], 1)}
        for sid, entry in _registry.items()
    }
