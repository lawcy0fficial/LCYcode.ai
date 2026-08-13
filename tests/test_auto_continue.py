import json
import asyncio

import lcycode.core.prompts as prompts
from lcycode.providers.base import Completion
from lcycode.config.key_manager import KeyManager
from lcycode.core.agent_loop import AgentLoop
from lcycode.core.session import Session


def test_auto_continue_chains_to_completion(tmp_path, monkeypatch):
    key_json = tmp_path / "key.json"
    key_json.write_text(json.dumps({
        "ollama": {"host": "http://x", "model": "m", "enabled": True, "offline_only": True},
        "routing": {"order": ["ollama"], "max_iterations": 1, "max_total_iterations": 10,
                    "auto_continue": True},
    }))

    state = {"review_calls": 0}

    async def fake_call_llm(messages, key_manager, prefer=None, tools=None, on_event=None, stage=None):
        user_msg = messages[-1]["content"]
        if tools:
            return "ollama", Completion(tool_calls=[
                {"function": {"name": "write_file",
                              "arguments": json.dumps({"path": "x.txt", "content": "x"})}}
            ])
        if "Task from the user" in user_msg:
            return "ollama", Completion(content=json.dumps({"summary": "s", "goals": [], "assumptions": []}))
        if "Task summary" in user_msg:
            return "ollama", Completion(content=json.dumps({"steps": [{"id": 1, "title": "t"}]}))
        if "Judge whether" in user_msg:
            state["review_calls"] += 1
            # needs 3 chunks (max_iterations=1 each) before it says complete
            return "ollama", Completion(content=json.dumps({"complete": state["review_calls"] >= 3}))
        raise AssertionError(user_msg[:150])

    monkeypatch.setattr(prompts, "call_llm", fake_call_llm)

    km = KeyManager(path=key_json)
    session = Session("auto-continue-test")
    loop = AgentLoop(km, session=session)

    result = asyncio.run(loop.run_to_completion("build x.txt"))

    assert result["complete"] is True
    assert result["iterations"] == 3  # three chunks of 1 iteration each, chained automatically
    assert session.has_pending is False


def test_auto_continue_off_stops_after_one_chunk(tmp_path, monkeypatch):
    key_json = tmp_path / "key.json"
    key_json.write_text(json.dumps({
        "ollama": {"host": "http://x", "model": "m", "enabled": True, "offline_only": True},
        "routing": {"order": ["ollama"], "max_iterations": 1, "max_total_iterations": 10,
                    "auto_continue": False},
    }))

    async def fake_call_llm(messages, key_manager, prefer=None, tools=None, on_event=None, stage=None):
        user_msg = messages[-1]["content"]
        if tools:
            return "ollama", Completion(tool_calls=[
                {"function": {"name": "write_file",
                              "arguments": json.dumps({"path": "x.txt", "content": "x"})}}
            ])
        if "Task from the user" in user_msg:
            return "ollama", Completion(content=json.dumps({"summary": "s", "goals": [], "assumptions": []}))
        if "Task summary" in user_msg:
            return "ollama", Completion(content=json.dumps({"steps": [{"id": 1, "title": "t"}]}))
        if "Judge whether" in user_msg:
            return "ollama", Completion(content=json.dumps({"complete": False}))
        raise AssertionError(user_msg[:150])

    monkeypatch.setattr(prompts, "call_llm", fake_call_llm)

    km = KeyManager(path=key_json)
    session = Session("auto-continue-off-test")
    loop = AgentLoop(km, session=session)

    result = asyncio.run(loop.run_to_completion("build x.txt"))

    assert result["complete"] is False
    assert result["iterations"] == 1  # stopped after the first chunk, no chaining
    assert session.has_pending is True


def test_auto_continue_stops_at_safety_ceiling(tmp_path, monkeypatch):
    key_json = tmp_path / "key.json"
    key_json.write_text(json.dumps({
        "ollama": {"host": "http://x", "model": "m", "enabled": True, "offline_only": True},
        "routing": {"order": ["ollama"], "max_iterations": 1, "max_total_iterations": 2,
                    "auto_continue": True},
    }))

    async def fake_call_llm(messages, key_manager, prefer=None, tools=None, on_event=None, stage=None):
        user_msg = messages[-1]["content"]
        if tools:
            return "ollama", Completion(tool_calls=[
                {"function": {"name": "write_file",
                              "arguments": json.dumps({"path": "x.txt", "content": "x"})}}
            ])
        if "Task from the user" in user_msg:
            return "ollama", Completion(content=json.dumps({"summary": "s", "goals": [], "assumptions": []}))
        if "Task summary" in user_msg:
            return "ollama", Completion(content=json.dumps({"steps": [{"id": 1, "title": "t"}]}))
        if "Judge whether" in user_msg:
            return "ollama", Completion(content=json.dumps({"complete": False}))  # never completes
        raise AssertionError(user_msg[:150])

    monkeypatch.setattr(prompts, "call_llm", fake_call_llm)

    km = KeyManager(path=key_json)
    session = Session("auto-continue-ceiling-test")
    loop = AgentLoop(km, session=session)

    result = asyncio.run(loop.run_to_completion("build x.txt forever"))

    assert result["complete"] is False
    assert result["iterations"] == 2  # stopped exactly at max_total_iterations, not beyond
