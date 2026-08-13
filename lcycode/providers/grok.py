"""Grok (xAI) provider — supports native tool calling."""
import httpx

from lcycode.providers.base import DEFAULT_TIMEOUT, ProviderError, Completion
from lcycode.providers.retry import with_retry

NAME = "grok"


@with_retry()
async def _post(client, key, model, messages, tools):
    body = {"model": model, "messages": messages}
    if tools:
        body["tools"] = tools
    r = await client.post(
        "https://api.x.ai/v1/chat/completions",
        headers={"Authorization": f"Bearer {key}"},
        json=body,
    )
    r.raise_for_status()
    return r.json()


async def call(messages, key_manager, tools=None, on_event=None, stage=None) -> Completion:
    cfg = key_manager.provider_config("grok")
    model = cfg.get("model", "grok-2-latest")
    key = key_manager.get_key("grok")
    if not key:
        raise ProviderError("no grok keys configured")
    async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
        try:
            data = await _post(client, key, model, messages, tools)
        except httpx.HTTPStatusError as e:
            if e.response.status_code in (401, 402, 429):
                key_manager.mark_failed("grok", key)
            raise ProviderError(f"grok HTTP {e.response.status_code}") from e
        except httpx.HTTPError as e:
            raise ProviderError(f"grok unreachable: {e}") from e
        msg = data["choices"][0]["message"]
        return Completion(content=msg.get("content"), tool_calls=msg.get("tool_calls"))
