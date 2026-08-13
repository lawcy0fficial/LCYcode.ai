"""
ollama.py
The core provider — LCYcode.ai is built around a fully offline
Ollama daemon running a local coding model. This adapter:
  - checks the daemon is actually reachable before calling it
  - verifies the configured model is pulled, and auto-pulls it on
    first use if key.json has ollama.auto_pull = true (default)
  - supports native tool calling for tool-capable local models
  - is the only provider used when ollama.offline_only = true
"""
import json

import httpx

from lcycode.providers.base import DEFAULT_TIMEOUT, ProviderError, Completion
from lcycode.providers.retry import with_retry
from lcycode.core.logging_utils import get_logger

NAME = "ollama"
PULL_TIMEOUT = 1800  # local model pulls can be large; give it room
log = get_logger(__name__)

_verified_models = set()  # per-process cache so we don't re-check every call


async def is_reachable(host: str, timeout: float = 3.0) -> bool:
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            r = await client.get(f"{host}/api/tags")
            return r.status_code == 200
    except httpx.HTTPError:
        return False


async def list_models(host: str) -> list:
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(f"{host}/api/tags")
        r.raise_for_status()
        return [m["name"] for m in r.json().get("models", [])]


async def _ensure_model(host: str, model: str, auto_pull: bool, on_event=None):
    cache_key = f"{host}::{model}"
    if cache_key in _verified_models:
        return
    try:
        models = await list_models(host)
    except httpx.HTTPError as e:
        raise ProviderError(f"ollama daemon unreachable at {host}: {e}") from e

    def matches(name):
        # "deepseek-coder:1.3b" should match a locally-tagged
        # "deepseek-coder:1.3b" exactly, or "deepseek-coder" loosely.
        return name == model or name.split(":")[0] == model.split(":")[0]

    if any(matches(m) for m in models):
        _verified_models.add(cache_key)
        return

    if not auto_pull:
        raise ProviderError(
            f"model '{model}' is not pulled in ollama and auto_pull is disabled. "
            f"Run: ollama pull {model}"
        )

    log.info("model %s not found locally — auto-pulling (this can take a while)", model)
    if on_event:
        on_event({"type": "ollama_pull_start", "model": model})
    async with httpx.AsyncClient(timeout=PULL_TIMEOUT) as client:
        async with client.stream("POST", f"{host}/api/pull", json={"name": model}) as r:
            if r.status_code != 200:
                raise ProviderError(f"failed to pull model {model}: HTTP {r.status_code}")
            async for _ in r.aiter_lines():
                pass  # drain the streamed progress; caller doesn't need it token-by-token
    if on_event:
        on_event({"type": "ollama_pull_done", "model": model})
    _verified_models.add(cache_key)


@with_retry()
async def _post(client, host, model, messages, tools):
    body = {"model": model, "messages": messages, "stream": False}
    if tools:
        body["tools"] = tools
    r = await client.post(f"{host}/api/chat", json=body)
    r.raise_for_status()
    return r.json()


async def _stream_call(host, model, messages, tools, on_event, stage):
    """Streams the response and emits a 'token' event per chunk of
    content as it arrives, so the GUI can render live-typing output
    instead of waiting for the full completion. Tool calls (when
    present) arrive fully-formed in the final chunk regardless of
    streaming — Ollama doesn't stream partial tool-call arguments —
    so only plain-text content actually streams token-by-token; a
    tool-call response still just shows up once, same as before.
    No retry wrapper here: retrying a partially-streamed response
    would mean replaying tokens already shown to the user, which is
    worse than just surfacing the failure.
    """
    body = {"model": model, "messages": messages, "stream": True}
    if tools:
        body["tools"] = tools
    content_parts = []
    tool_calls = None
    async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
        try:
            async with client.stream("POST", f"{host}/api/chat", json=body) as r:
                if r.status_code != 200:
                    body_text = await r.aread()
                    raise ProviderError(f"ollama call failed: HTTP {r.status_code}: {body_text[:200]!r}")
                async for line in r.aiter_lines():
                    if not line:
                        continue
                    try:
                        chunk = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    msg = chunk.get("message", {})
                    delta = msg.get("content", "")
                    if delta:
                        content_parts.append(delta)
                        on_event({"type": "token", "stage": stage, "delta": delta})
                    if msg.get("tool_calls"):
                        tool_calls = msg["tool_calls"]
                    if chunk.get("done"):
                        break
        except httpx.HTTPError as e:
            raise ProviderError(f"ollama streaming call failed: {e}") from e
    return Completion(content="".join(content_parts) or None, tool_calls=tool_calls)


async def call(messages, key_manager, tools=None, on_event=None, stage=None) -> Completion:
    cfg = key_manager.provider_config("ollama")
    if not cfg.get("enabled", True):
        raise ProviderError("ollama disabled in key.json")
    host = cfg.get("host", "http://127.0.0.1:11434")
    model = cfg.get("model", "deepseek-coder:1.3b")
    auto_pull = cfg.get("auto_pull", True)

    if not await is_reachable(host):
        raise ProviderError(
            f"ollama daemon not reachable at {host} — is it running? "
            f"(the offline model path is unavailable until it is)"
        )
    await _ensure_model(host, model, auto_pull, on_event)

    if on_event is not None:
        return await _stream_call(host, model, messages, tools, on_event, stage)

    async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
        try:
            data = await _post(client, host, model, messages, tools)
        except httpx.HTTPError as e:
            raise ProviderError(f"ollama call failed: {e}") from e
        msg = data.get("message", {})
        return Completion(content=msg.get("content"), tool_calls=msg.get("tool_calls"))
