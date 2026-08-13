"""OpenRouter provider — rotates keys and free models (incl. NVIDIA Nemotron),
supports native OpenAI-style tool calling."""
import httpx

from lcycode.providers.base import DEFAULT_TIMEOUT, ProviderError, Completion
from lcycode.providers.retry import with_retry

NAME = "openrouter"
DEFAULT_MODELS = ["nvidia/llama-3.1-nemotron-70b-instruct:free"]


@with_retry()
async def _post(client, key, model, messages, tools):
    body = {"model": model, "messages": messages}
    if tools:
        body["tools"] = tools
    r = await client.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {key}",
            "HTTP-Referer": "https://lcycode.local",
            "X-Title": "LCYcode.ai",
        },
        json=body,
    )
    r.raise_for_status()
    return r.json()


async def call(messages, key_manager, tools=None, on_event=None, stage=None) -> Completion:
    cfg = key_manager.provider_config("openrouter")
    models = cfg.get("models") or DEFAULT_MODELS
    key = key_manager.get_key("openrouter")
    if not key:
        raise ProviderError("no openrouter keys configured")

    last_err = None
    async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
        for model in models:
            try:
                data = await _post(client, key, model, messages, tools)
                msg = data["choices"][0]["message"]
                return Completion(content=msg.get("content"), tool_calls=msg.get("tool_calls"))
            except httpx.HTTPStatusError as e:
                if e.response.status_code in (401, 402, 429):
                    key_manager.mark_failed("openrouter", key)
                last_err = f"{model}: HTTP {e.response.status_code}"
                continue
            except httpx.HTTPError as e:
                last_err = str(e)
                continue
    raise ProviderError(f"openrouter exhausted: {last_err}")
