"""
router.py
Dispatches a chat completion to providers in the configured routing
order (default: ollama -> openrouter -> deepseek -> grok), falling
through to the next provider if one raises ProviderError. Optionally
passes an OpenAI-compatible `tools` schema through for native
function calling.

Ollama is the only provider required or expected to be used — the
others (OpenRouter/DeepSeek/Grok) are optional cloud fallback, off by
default (see key.json's offline_only). There is deliberately no
Anthropic API provider here: if you want to work with Claude Code
against this project's Ollama setup, use setup-claude-code.sh, which
runs the real Claude Code CLI directly against Ollama — no Anthropic
account, login, or API key involved anywhere.
"""
from lcycode.providers import ollama, openrouter, deepseek, grok
from lcycode.providers.base import ProviderError
from lcycode.core.logging_utils import get_logger

log = get_logger(__name__)

_DISPATCH = {
    ollama.NAME: ollama.call,
    openrouter.NAME: openrouter.call,
    deepseek.NAME: deepseek.call,
    grok.NAME: grok.call,
}


async def call_llm(messages, key_manager, prefer=None, tools=None, on_event=None, stage=None):
    """Returns (provider_name, Completion). If on_event is given, the
    ollama provider streams tokens through it as 'token' events (see
    ollama.py) — the only provider that does, since it's the core,
    always-available one; cloud providers accept and ignore the kwarg
    so the call signature stays uniform across all four."""
    if key_manager.offline_only() and prefer and prefer != "ollama":
        log.warning("offline_only is set — ignoring prefer=%r, forcing ollama", prefer)
        prefer = "ollama"
    order = [prefer] if prefer else key_manager.routing().get("order", list(_DISPATCH))
    errors = []
    for provider in order:
        fn = _DISPATCH.get(provider)
        if not fn:
            continue
        try:
            completion = await fn(messages, key_manager, tools=tools, on_event=on_event, stage=stage)
            return provider, completion
        except Exception as e:  # noqa: BLE001 - intentionally broad: fall through
            log.warning("provider %s failed, falling through: %s", provider, e)
            errors.append(f"{provider}: {e}")
            continue
    raise ProviderError("All providers failed:\n" + "\n".join(errors))
