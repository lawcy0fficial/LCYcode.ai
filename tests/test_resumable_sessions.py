from lcycode.core.session import Session, SESSIONS_DIR


def _cleanup(session_id):
    path = SESSIONS_DIR / f"{session_id}.json"
    if path.exists():
        path.unlink()


def test_set_pending_then_has_pending_true():
    _cleanup("pending-test-1")
    s = Session("pending-test-1")
    assert s.has_pending is False
    s.set_pending("build a game", {"summary": "a game"}, [{"id": 1, "title": "step 1"}], [])
    assert s.has_pending is True
    assert s.data["pending"]["user_task"] == "build a game"
    _cleanup("pending-test-1")


def test_clear_pending_resets_state():
    _cleanup("pending-test-2")
    s = Session("pending-test-2")
    s.set_pending("build a game", {"summary": "a game"}, [], [])
    s.clear_pending()
    assert s.has_pending is False
    assert s.data["pending"] is None
    _cleanup("pending-test-2")


def test_pending_survives_reload():
    _cleanup("pending-test-3")
    s1 = Session("pending-test-3")
    s1.set_pending("build a game", {"summary": "a game"}, [{"id": 1}], [{"tool": "write_file"}])

    s2 = Session("pending-test-3")
    assert s2.has_pending is True
    assert s2.data["pending"]["log"] == [{"tool": "write_file"}]
    _cleanup("pending-test-3")
