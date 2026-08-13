from lcycode.core import run_registry


def test_register_returns_a_fresh_unset_event():
    event = run_registry.register("reg-test-1")
    assert event.is_set() is False
    run_registry.unregister("reg-test-1")


def test_request_cancel_sets_the_event_and_returns_true():
    event = run_registry.register("reg-test-2")
    was_running = run_registry.request_cancel("reg-test-2")
    assert was_running is True
    assert event.is_set() is True
    run_registry.unregister("reg-test-2")


def test_request_cancel_on_unknown_session_returns_false():
    assert run_registry.request_cancel("nonexistent-session-xyz") is False


def test_unregister_then_cancel_returns_false():
    run_registry.register("reg-test-3")
    run_registry.unregister("reg-test-3")
    assert run_registry.request_cancel("reg-test-3") is False


def test_is_running_reflects_registration_state():
    assert run_registry.is_running("reg-test-4") is False
    run_registry.register("reg-test-4")
    assert run_registry.is_running("reg-test-4") is True
    run_registry.unregister("reg-test-4")
    assert run_registry.is_running("reg-test-4") is False


def test_status_lists_registered_sessions():
    run_registry.register("reg-test-5")
    status = run_registry.status()
    assert "reg-test-5" in status
    assert "running_for_seconds" in status["reg-test-5"]
    run_registry.unregister("reg-test-5")
    assert "reg-test-5" not in run_registry.status()


def test_register_overwrites_a_stale_entry_for_the_same_session():
    event1 = run_registry.register("reg-test-6")
    event2 = run_registry.register("reg-test-6")  # simulates a second run starting for the same session
    assert event1 is not event2
    # cancelling now only affects the current (second) registration
    run_registry.request_cancel("reg-test-6")
    assert event2.is_set() is True
    assert event1.is_set() is False
    run_registry.unregister("reg-test-6")
