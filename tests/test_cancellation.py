import json
import asyncio

import lcycode.core.prompts as prompts
from lcycode.providers.base import Completion
from lcycode.config.key_manager import KeyManager
from lcycode.core.agent_loop import AgentLoop
from lcycode.core.session import Session


def _base_key_json(tmp_path, max_iterations=10):
    key_json = tmp_path / "key.json"
    key_json.write_text(json.dumps({
        "ollama": {"host": "http://x", "model": "m", "enabled": True, "offline_only": True},
        "routing": {"order": ["ollama"], "max_iterations": max_iterations,
                    "max_total_iterations": 100, "auto_continue": True},
    }))
    return key_json


def test_cancel_before_run_starts_returns_immediately_cancelled(tmp_path, monkeypatch):
    async def fake_call_llm(*a, **k):
        raise AssertionError("should never call the model — cancelled before DESCRIBE")

    monkeypatch.setattr(prompts, "call_llm", fake_call_llm)

    km = KeyManager(path=_base_key_json(tmp_path))
    session = Session("cancel-before-start")
    cancel_event = asyncio.Event()
    cancel_event.set()  # already cancelled before the run even begins
    loop = AgentLoop(km, session=session, cancel_event=cancel_event)

    result = asyncio.run(loop.run("do something"))
    assert result["cancelled"] is True
    assert result["complete"] is False
    assert result["iterations"] == 0


def test_cancel_mid_execute_review_stops_at_next_checkpoint(tmp_path, monkeypatch):
    call_count = {"execute": 0}
    cancel_event = asyncio.Event()

    async def fake_call_llm(messages, key_manager, prefer=None, tools=None, on_event=None, stage=None):
        user_msg = messages[-1]["content"]
        if "Task from the user" in user_msg:
            return "ollama", Completion(content=json.dumps({"summary": "s", "goals": [], "assumptions": []}))
        if "Task summary" in user_msg:
            return "ollama", Completion(content=json.dumps({"steps": [{"id": 1, "title": "t"}]}))
        if tools:
            call_count["execute"] += 1
            if call_count["execute"] == 2:
                # simulate a cancel request arriving while the second
                # EXECUTE call is already in flight — it should still
                # complete this tool call, then stop before REVIEW.
                cancel_event.set()
            return "ollama", Completion(tool_calls=[
                {"function": {"name": "write_file", "arguments": json.dumps({"path": "x.txt", "content": "x"})}}
            ])
        if "Judge whether" in user_msg:
            return "ollama", Completion(content=json.dumps({"complete": False}))  # never completes on its own
        raise AssertionError(user_msg[:150])

    monkeypatch.setattr(prompts, "call_llm", fake_call_llm)

    km = KeyManager(path=_base_key_json(tmp_path, max_iterations=10))
    session = Session("cancel-mid-run")
    loop = AgentLoop(km, session=session, cancel_event=cancel_event)

    result = asyncio.run(loop.run_to_completion("build x.txt"))

    assert result["cancelled"] is True
    assert result["complete"] is False
    # exactly 2 EXECUTE calls happened before the cooperative check caught the cancel
    assert call_count["execute"] == 2
    assert session.has_pending is True  # cancelled runs still checkpoint for later resume


def test_cancelled_run_is_resumable_via_continue_run(tmp_path, monkeypatch):
    state = {"execute_calls": 0}
    cancel_event = asyncio.Event()

    async def fake_call_llm(messages, key_manager, prefer=None, tools=None, on_event=None, stage=None):
        user_msg = messages[-1]["content"]
        if "Task from the user" in user_msg:
            return "ollama", Completion(content=json.dumps({"summary": "s", "goals": [], "assumptions": []}))
        if "Task summary" in user_msg:
            return "ollama", Completion(content=json.dumps({"steps": [{"id": 1, "title": "t"}]}))
        if tools:
            state["execute_calls"] += 1
            return "ollama", Completion(tool_calls=[
                {"function": {"name": "write_file", "arguments": json.dumps({"path": "x.txt", "content": "x"})}}
            ])
        if "Judge whether" in user_msg:
            # complete only after the resume's execute call happens
            return "ollama", Completion(content=json.dumps({"complete": state["execute_calls"] >= 1}))
        raise AssertionError(user_msg[:150])

    monkeypatch.setattr(prompts, "call_llm", fake_call_llm)

    km = KeyManager(path=_base_key_json(tmp_path, max_iterations=10))
    session = Session("cancel-then-resume")
    loop = AgentLoop(km, session=session, cancel_event=cancel_event)
    cancel_event.set()  # cancel immediately so the first run does nothing but checkpoint

    result = asyncio.run(loop.run("build x.txt"))
    assert result["cancelled"] is True
    assert session.has_pending is True
    assert state["execute_calls"] == 0  # cancelled before EXECUTE ever ran

    # resume with a fresh (unset) cancel event, same session
    fresh_loop = AgentLoop(km, session=session, cancel_event=asyncio.Event())
    resumed = asyncio.run(fresh_loop.continue_run(session.data["pending"]))
    assert resumed["complete"] is True
    assert state["execute_calls"] == 1
