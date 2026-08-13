import json
import asyncio

from lcycode.providers import ollama


def _fake_reachable_and_verified(monkeypatch):
    async def fake_is_reachable(host, timeout=3.0):
        return True
    monkeypatch.setattr(ollama, "is_reachable", fake_is_reachable)

    async def fake_ensure_model(host, model, auto_pull, on_event=None):
        return None
    monkeypatch.setattr(ollama, "_ensure_model", fake_ensure_model)


def test_streaming_call_emits_token_events_and_returns_full_content(monkeypatch):
    _fake_reachable_and_verified(monkeypatch)

    ndjson_lines = [
        json.dumps({"message": {"content": "Hello"}, "done": False}),
        json.dumps({"message": {"content": ", "}, "done": False}),
        json.dumps({"message": {"content": "world"}, "done": False}),
        json.dumps({"message": {"content": ""}, "done": True}),
    ]

    class FakeStreamResponse:
        status_code = 200

        async def aiter_lines(self):
            for line in ndjson_lines:
                yield line

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

    class FakeClient:
        def stream(self, method, url, json=None):
            return FakeStreamResponse()

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

    monkeypatch.setattr(ollama.httpx, "AsyncClient", lambda **kw: FakeClient())

    class KM:
        def provider_config(self, name):
            return {"enabled": True, "host": "http://x", "model": "m", "auto_pull": True}

    events = []
    completion = asyncio.run(ollama.call(
        [{"role": "user", "content": "hi"}], KM(), on_event=events.append, stage="DESCRIBE"
    ))

    token_events = [e for e in events if e["type"] == "token"]
    assert [e["delta"] for e in token_events] == ["Hello", ", ", "world"]
    assert all(e["stage"] == "DESCRIBE" for e in token_events)
    assert completion.content == "Hello, world"


def test_streaming_call_captures_tool_calls_from_final_chunk(monkeypatch):
    _fake_reachable_and_verified(monkeypatch)

    ndjson_lines = [
        json.dumps({"message": {"content": ""}, "done": False}),
        json.dumps({
            "message": {"content": "", "tool_calls": [
                {"function": {"name": "write_file", "arguments": {"path": "x.txt", "content": "hi"}}}
            ]},
            "done": True,
        }),
    ]

    class FakeStreamResponse:
        status_code = 200

        async def aiter_lines(self):
            for line in ndjson_lines:
                yield line

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

    class FakeClient:
        def stream(self, method, url, json=None):
            return FakeStreamResponse()

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

    monkeypatch.setattr(ollama.httpx, "AsyncClient", lambda **kw: FakeClient())

    class KM:
        def provider_config(self, name):
            return {"enabled": True, "host": "http://x", "model": "m", "auto_pull": True}

    events = []
    completion = asyncio.run(ollama.call(
        [{"role": "user", "content": "hi"}], KM(), on_event=events.append, stage="EXECUTE"
    ))

    assert completion.has_tool_call is True
    assert completion.tool_calls[0]["function"]["name"] == "write_file"


def test_non_streaming_path_used_when_no_on_event(monkeypatch):
    _fake_reachable_and_verified(monkeypatch)

    class FakeResponse:
        status_code = 200
        def raise_for_status(self):
            pass
        def json(self):
            return {"message": {"content": "no streaming here"}}

    class FakeClient:
        async def post(self, url, json=None):
            return FakeResponse()

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

    monkeypatch.setattr(ollama.httpx, "AsyncClient", lambda **kw: FakeClient())

    class KM:
        def provider_config(self, name):
            return {"enabled": True, "host": "http://x", "model": "m", "auto_pull": True}

    completion = asyncio.run(ollama.call([{"role": "user", "content": "hi"}], KM()))
    assert completion.content == "no streaming here"
