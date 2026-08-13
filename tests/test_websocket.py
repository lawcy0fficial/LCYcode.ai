import json
import asyncio

from fastapi.testclient import TestClient

import lcycode.core.prompts as prompts
from lcycode.providers.base import Completion
from lcycode.api.server import app


def _fake_call_llm_factory(complete_after_reviews=1):
    """For tests that want a run to actually finish after N review
    cycles. NOT safe for tests that need a run to stay in-flight for
    an unbounded/uncertain amount of real time — see _never_completes
    below for that case, and the note on why this distinction matters."""
    state = {"reviews": 0}

    async def fake_call_llm(messages, key_manager, prefer=None, tools=None, on_event=None, stage=None):
        user_msg = messages[-1]["content"]
        if "Task from the user" in user_msg:
            return "ollama", Completion(content=json.dumps({"summary": "s", "goals": [], "assumptions": []}))
        if "Task summary" in user_msg:
            return "ollama", Completion(content=json.dumps({"steps": [{"id": 1, "title": "t"}]}))
        if tools:
            return "ollama", Completion(tool_calls=[
                {"function": {"name": "write_file", "arguments": json.dumps({"path": "x.txt", "content": "hi"})}}
            ])
        if "Judge whether" in user_msg:
            state["reviews"] += 1
            return "ollama", Completion(content=json.dumps({"complete": state["reviews"] >= complete_after_reviews}))
        raise AssertionError(user_msg[:150])

    return fake_call_llm


async def _never_completes(messages, key_manager, prefer=None, tools=None, on_event=None, stage=None):
    """Unconditionally never says complete. Tests that need a run to
    stay genuinely in-flight (to test cancellation, or that a second
    'start' for the same session gets rejected) must use this rather
    than a fake with a finite completion threshold like
    'complete after N reviews' — with an instant fake provider (no
    real network I/O), hundreds of iterations can finish in
    milliseconds via auto_continue, so a numeric threshold can race
    against and beat whatever the test does next in real wall-clock
    time. That raced two different tests here intermittently before
    this fix (flaky ~40% of runs) — unconditional False removes the
    race entirely rather than just making it less likely."""
    user_msg = messages[-1]["content"]
    if "Task from the user" in user_msg:
        return "ollama", Completion(content=json.dumps({"summary": "s", "goals": [], "assumptions": []}))
    if "Task summary" in user_msg:
        return "ollama", Completion(content=json.dumps({"steps": [{"id": 1, "title": "t"}]}))
    if tools:
        return "ollama", Completion(tool_calls=[
            {"function": {"name": "write_file", "arguments": json.dumps({"path": "x.txt", "content": "x"})}}
        ])
    if "Judge whether" in user_msg:
        return "ollama", Completion(content=json.dumps({"complete": False}))
    raise AssertionError(user_msg[:150])


def test_websocket_start_streams_events_to_completion(monkeypatch):
    monkeypatch.setattr(prompts, "call_llm", _fake_call_llm_factory(complete_after_reviews=1))
    client = TestClient(app)

    with client.websocket_connect("/ws/chat") as ws:
        ws.send_json({"action": "start", "message": "build x.txt"})

        events = []
        while True:
            event = ws.receive_json()
            events.append(event)
            if event["type"] == "final":
                break

    types_seen = [e["type"] for e in events]
    assert "session" in types_seen
    assert "stage" in types_seen
    assert "tool_call" in types_seen
    final = next(e for e in events if e["type"] == "final")
    assert final["data"]["complete"] is True


def test_websocket_cancel_mid_run_stops_the_loop(monkeypatch):
    monkeypatch.setattr(prompts, "call_llm", _never_completes)
    client = TestClient(app)

    with client.websocket_connect("/ws/chat") as ws:
        ws.send_json({"action": "start", "message": "build x.txt forever", "session_id": "ws-cancel-test"})

        session_event = ws.receive_json()
        assert session_event["type"] == "session"
        session_id = session_event["session_id"]

        # let a couple of tool calls happen, then cancel over the same socket
        seen_tool_calls = 0
        cancelled_sent = False
        while True:
            event = ws.receive_json()
            if event["type"] == "tool_call":
                seen_tool_calls += 1
                if seen_tool_calls == 2 and not cancelled_sent:
                    ws.send_json({"action": "cancel", "session_id": session_id})
                    cancelled_sent = True
            if event["type"] == "final":
                assert event["data"]["cancelled"] is True
                break

    assert seen_tool_calls >= 2


def test_websocket_continue_action_reports_nothing_to_continue_cleanly():
    client = TestClient(app)
    with client.websocket_connect("/ws/chat") as ws:
        ws.send_json({"action": "continue", "session_id": "ws-continue-empty-test"})
        event = ws.receive_json()
        assert event["type"] == "error"
        assert "nothing to continue" in event["message"]


def test_websocket_unknown_action_returns_error():
    client = TestClient(app)
    with client.websocket_connect("/ws/chat") as ws:
        ws.send_json({"action": "not_a_real_action"})
        event = ws.receive_json()
        assert event["type"] == "error"
        assert "unknown action" in event["message"]


def test_websocket_two_sessions_run_concurrently_on_one_connection(monkeypatch):
    """The actual multiplexing claim: session B can start and finish
    WHILE session A is still genuinely in flight on the SAME
    connection. Session A is given a real async delay in its tool
    call so the interleaving is deterministic in effect (B provably
    finishes first), even though the exact event ORDER between two
    genuinely concurrent tasks is legitimately nondeterministic and
    not something this test should assert on."""
    async def fake_call_llm(messages, key_manager, prefer=None, tools=None, on_event=None, stage=None):
        user_msg = messages[-1]["content"]
        # The original task text ("build a"/"build b") only appears in the
        # DESCRIBE prompt — later stages only see what DESCRIBE/PLAN
        # returned, not the raw task, so the "which session" marker has
        # to be threaded through the summary/steps text itself, same as
        # the real prompts.py flow actually carries context forward.
        if "Task from the user" in user_msg:
            which = "a" if "build a" in user_msg else "b"
            return "ollama", Completion(content=json.dumps(
                {"summary": f"s-{which}", "goals": [], "assumptions": []}))
        if "Task summary" in user_msg:
            which = "a" if "s-a" in user_msg else "b"
            return "ollama", Completion(content=json.dumps(
                {"steps": [{"id": 1, "title": f"write for {which}"}]}))
        if tools:
            if "write for a" in user_msg:
                await asyncio.sleep(0.3)  # keeps session A genuinely in-flight
            return "ollama", Completion(tool_calls=[
                {"function": {"name": "write_file", "arguments": json.dumps({"path": "x.txt", "content": "hi"})}}
            ])
        if "Judge whether" in user_msg:
            return "ollama", Completion(content=json.dumps({"complete": True}))
        raise AssertionError(user_msg[:150])

    monkeypatch.setattr(prompts, "call_llm", fake_call_llm)
    client = TestClient(app)

    with client.websocket_connect("/ws/chat") as ws:
        ws.send_json({"action": "start", "message": "build a", "session_id": "multiplex-a"})
        session_event_a = ws.receive_json()
        assert session_event_a == {"type": "session", "session_id": "multiplex-a"}

        # A is now inside its 0.3s sleep — start B WHILE that's true. This
        # is exactly what the old single-run-per-connection version
        # rejected outright.
        ws.send_json({"action": "start", "message": "build b", "session_id": "multiplex-b"})

        events = {"multiplex-a": [], "multiplex-b": []}
        session_acks_seen = {"multiplex-a"}  # consumed above, before the loop starts
        final_order = []
        while len(final_order) < 2:
            event = ws.receive_json()
            sid = event.get("session_id")
            assert sid in ("multiplex-a", "multiplex-b"), f"untagged or misrouted event: {event}"
            events[sid].append(event)
            if event["type"] == "session":
                session_acks_seen.add(sid)
            if event["type"] == "final":
                final_order.append(sid)

    assert session_acks_seen == {"multiplex-a", "multiplex-b"}
    a_final = next(e for e in events["multiplex-a"] if e["type"] == "final")
    b_final = next(e for e in events["multiplex-b"] if e["type"] == "final")
    assert a_final["data"]["complete"] is True
    assert b_final["data"]["complete"] is True
    # the actual proof of concurrency: B (no delay) finishes before A
    # (0.3s delay) despite starting second — impossible if the server
    # had secretly serialized them behind one run-at-a-time queue.
    assert final_order == ["multiplex-b", "multiplex-a"]


def test_websocket_second_start_for_same_session_is_rejected(monkeypatch):
    """Multiplexing is per-DISTINCT-session, not unlimited — starting the
    same session twice concurrently is still correctly rejected."""
    monkeypatch.setattr(prompts, "call_llm", _never_completes)
    client = TestClient(app)

    with client.websocket_connect("/ws/chat") as ws:
        ws.send_json({"action": "start", "message": "build x", "session_id": "dup-session-test"})
        session_event = ws.receive_json()
        assert session_event["type"] == "session"

        ws.send_json({"action": "start", "message": "build x again", "session_id": "dup-session-test"})
        # The rejection is emitted immediately once receiver() actually
        # processes the second message, but asyncio doesn't guarantee
        # how many other ready callbacks run first — a task whose awaits
        # (asyncio.to_thread dispatching a near-instant synchronous file
        # write) keep completing and re-queuing themselves essentially
        # immediately can dominate the event loop's ready queue for a
        # while before the receiver's already-ready read gets its turn.
        # That's real, observed scheduling behavior (confirmed by
        # instrumenting this exact test — 16+ intervening events before
        # the rejection arrived, every single time, never absent), not
        # a sign the rejection doesn't happen. A generous bound here is
        # about correctness under real scheduling, not a magic number.
        error_event = None
        for _ in range(500):
            event = ws.receive_json()
            if event["type"] == "error" and "already in progress" in event.get("message", ""):
                error_event = event
                break
        assert error_event is not None
        assert error_event["session_id"] == "dup-session-test"

        ws.send_json({"action": "cancel", "session_id": "dup-session-test"})
