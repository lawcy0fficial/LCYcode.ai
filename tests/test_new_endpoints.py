from fastapi.testclient import TestClient

from lcycode.api.server import app
from lcycode.core import run_registry
from lcycode.core.session import Session, SESSIONS_DIR


def _cleanup_session(session_id):
    path = SESSIONS_DIR / f"{session_id}.json"
    if path.exists():
        path.unlink()


def test_cancel_endpoint_returns_false_when_nothing_running():
    client = TestClient(app)
    r = client.post("/api/chat/cancel", json={"session_id": "no-such-run"})
    assert r.status_code == 200
    assert r.json()["was_running"] is False


def test_cancel_endpoint_returns_true_and_sets_event_when_running():
    client = TestClient(app)
    event = run_registry.register("cancel-endpoint-test")
    try:
        r = client.post("/api/chat/cancel", json={"session_id": "cancel-endpoint-test"})
        assert r.json()["was_running"] is True
        assert event.is_set() is True
    finally:
        run_registry.unregister("cancel-endpoint-test")


def test_health_endpoint_shape():
    client = TestClient(app)
    r = client.get("/api/health")
    assert r.status_code == 200
    data = r.json()
    assert "status" in data
    assert "ollama_reachable" in data
    assert "offline_only" in data
    assert "runs_in_flight" in data


def test_sessions_endpoint_lists_a_created_session():
    _cleanup_session("sessions-list-test")
    session = Session("sessions-list-test")
    session.add_turn("build something", {"description": {"summary": "built something"}, "iterations": 2})

    client = TestClient(app)
    r = client.get("/api/sessions")
    assert r.status_code == 200
    ids = [s["session_id"] for s in r.json()["sessions"]]
    assert "sessions-list-test" in ids

    entry = next(s for s in r.json()["sessions"] if s["session_id"] == "sessions-list-test")
    assert entry["turn_count"] == 1
    assert entry["last_summary"] == "built something"
    assert entry["has_pending"] is False
    assert entry["currently_running"] is False

    _cleanup_session("sessions-list-test")


def test_sessions_endpoint_reflects_currently_running():
    _cleanup_session("sessions-running-test")
    session = Session("sessions-running-test")
    session.save()  # Session() alone doesn't write to disk until something's saved
    run_registry.register("sessions-running-test")
    try:
        client = TestClient(app)
        r = client.get("/api/sessions")
        entry = next(s for s in r.json()["sessions"] if s["session_id"] == "sessions-running-test")
        assert entry["currently_running"] is True
    finally:
        run_registry.unregister("sessions-running-test")
        _cleanup_session("sessions-running-test")


def test_sessions_endpoint_synthesizes_entry_for_unsaved_in_flight_session():
    """A session running its first chunk hasn't checkpointed to disk
    yet — it should still show up as currently_running, not be
    invisible until its first save()."""
    _cleanup_session("sessions-never-saved-test")
    run_registry.register("sessions-never-saved-test")
    try:
        client = TestClient(app)
        r = client.get("/api/sessions")
        entry = next(s for s in r.json()["sessions"] if s["session_id"] == "sessions-never-saved-test")
        assert entry["currently_running"] is True
        assert entry["turn_count"] == 0
    finally:
        run_registry.unregister("sessions-never-saved-test")
        _cleanup_session("sessions-never-saved-test")
