from lcycode.core.session import Session, SESSIONS_DIR


def _cleanup(session_id):
    path = SESSIONS_DIR / f"{session_id}.json"
    if path.exists():
        path.unlink()


def test_session_persists_across_instances():
    _cleanup("test-session-abc")
    s1 = Session("test-session-abc")
    s1.add_turn("build a cli tool", {"description": {"summary": "built a cli tool"}, "iterations": 3})

    s2 = Session("test-session-abc")
    assert len(s2.data["turns"]) == 1
    assert "cli tool" in s2.history_context()
    _cleanup("test-session-abc")


def test_new_session_has_empty_history_context():
    _cleanup("brand-new-session-id")
    s = Session("brand-new-session-id")
    assert s.history_context() == ""
    _cleanup("brand-new-session-id")
