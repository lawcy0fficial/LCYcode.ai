import asyncio

import httpx

from lcycode.providers import ollama


def test_is_reachable_false_on_connection_error(monkeypatch):
    class DummyClient:
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def get(self, url):
            raise httpx.ConnectError("refused", request=httpx.Request("GET", url))

    monkeypatch.setattr(ollama.httpx, "AsyncClient", lambda **kw: DummyClient())
    assert asyncio.run(ollama.is_reachable("http://127.0.0.1:11434")) is False


def test_is_reachable_true_on_200(monkeypatch):
    class DummyResponse:
        status_code = 200

    class DummyClient:
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def get(self, url):
            return DummyResponse()

    monkeypatch.setattr(ollama.httpx, "AsyncClient", lambda **kw: DummyClient())
    assert asyncio.run(ollama.is_reachable("http://127.0.0.1:11434")) is True
