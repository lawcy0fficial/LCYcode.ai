"""
EXECUTE stage — pick the next incomplete step and carry it out.

Prefers native tool calling (the model returns a real OpenAI-style
tool_call, which providers like OpenRouter/DeepSeek/Grok/newer Ollama
support directly). Falls back to asking for a JSON-described tool
call in prose for models/providers that don't honor tool schemas -
so the loop keeps working either way.
"""
import json

from lcycode.core.json_utils import extract_json
from lcycode.core.prompts import ask_stage_with_tools, ask_stage
from lcycode.core.logging_utils import get_logger
from lcycode.tools.registry import TOOL_SCHEMA

log = get_logger(__name__)
_warned_models = set()  # only nag once per model per process, not every step

_INSTRUCTIONS = (
    "Plan steps:\n{steps}\n\n"
    "Already completed (with results):\n{log}\n\n"
    "Call exactly one tool to carry out the single next incomplete step. "
    "If every step is already complete, do not call a tool - just reply with "
    'the text DONE.'
)

_JSON_FALLBACK_INSTRUCTIONS = (
    "Plan steps:\n{steps}\n\n"
    "Already completed (with results):\n{log}\n\n"
    "Pick the single next step that has not been completed yet and carry it "
    "out by emitting exactly one tool call. Respond with JSON: "
    '{{"tool": "<tool name>", "args": {{...}}, '
    '"note": "short human-readable description of what you are doing"}}. '
    'If every step is already complete, respond with {{"done": true}}.'
)


async def run(steps, completed_log, key_manager, on_event):
    prompt = _INSTRUCTIONS.format(steps=json.dumps(steps), log=json.dumps(completed_log[-10:]))
    provider, completion = await ask_stage_with_tools(
        "EXECUTE", prompt, key_manager, on_event, TOOL_SCHEMA
    )

    if completion.has_tool_call:
        call = completion.tool_calls[0]
        fn = call.get("function", call)  # some providers nest under "function"
        name = fn.get("name")
        raw_args = fn.get("arguments", "{}")
        args = json.loads(raw_args) if isinstance(raw_args, str) else (raw_args or {})
        return {"tool": name, "args": args, "note": f"native tool call via {provider}"}

    text = (completion.content or "").strip()
    if text.upper().startswith("DONE"):
        return {"done": True}

    if provider == "ollama":
        _warn_if_weak_tool_calling(key_manager, on_event)

    # Fallback: some models ignore the tool schema and just talk. Ask once
    # more, explicitly in JSON-description mode, instead of failing the loop.
    fallback_prompt = _JSON_FALLBACK_INSTRUCTIONS.format(
        steps=json.dumps(steps), log=json.dumps(completed_log[-10:])
    )
    try:
        return await ask_stage("EXECUTE", fallback_prompt, key_manager, on_event)
    except ValueError:
        return extract_json(text) if text else {"done": True}


def _warn_if_weak_tool_calling(key_manager, on_event):
    from lcycode.config.model_capabilities import lookup

    model = key_manager.provider_config("ollama").get("model", "")
    if model in _warned_models:
        return
    _warned_models.add(model)
    support = lookup(model)
    if support in ("limited", "unknown"):
        message = (
            f"'{model}' didn't return a native tool call and is falling back to "
            f"JSON-mode ({support} known tool-calling support). This still works but "
            f"is slower/less reliable. Consider a tool-tuned model like qwen2.5-coder:7b."
        )
        log.info(message)
        on_event({"type": "tool_calling_fallback_hint", "model": model,
                  "support": support, "message": message})
