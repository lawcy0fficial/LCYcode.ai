"""Shared system prompt plus the stage-calling helpers every stage module uses."""
from lcycode.providers.router import call_llm
from lcycode.core.json_utils import extract_json

SYSTEM_PROMPT = """You are LCYcode.ai, an autonomous coding agent with access to a \
sandboxed workspace and a set of tools for writing, editing, and running code. \
Use the tools available to you to accomplish the user's task."""

JSON_SYSTEM_PROMPT = SYSTEM_PROMPT + """

For this stage, respond with a SINGLE JSON object and nothing else - no prose \
outside the JSON, no markdown fences. The schema is given in the user message."""


async def ask_stage(stage_name, user_content, key_manager, on_event, prefer=None):
    """JSON-mode stage call (DESCRIBE / PLAN / REVIEW): asks the model
    for structured JSON and parses it. No tools are offered here.
    on_event is passed through to call_llm so ollama can stream
    tokens live as the JSON is generated — the GUI shows this as a
    transient "thinking" bubble, separate from the parsed result
    message that lands once the full JSON is valid."""
    messages = [
        {"role": "system", "content": JSON_SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]
    provider, completion = await call_llm(
        messages, key_manager, prefer=prefer, on_event=on_event, stage=stage_name
    )
    text = completion.content or ""
    on_event({"type": "model_response", "stage": stage_name, "provider": provider, "text": text})
    return extract_json(text)


async def ask_stage_with_tools(stage_name, user_content, key_manager, on_event,
                                tool_schema, prefer=None):
    """Tool-calling stage call (EXECUTE): offers the model the real
    tool schema. Returns (provider, completion) so the caller can
    check completion.has_tool_call and branch accordingly, falling
    back to JSON-content parsing for providers/models that ignore
    tool schemas and just answer in prose. Streaming still applies
    to any plain-text content — Ollama doesn't stream tool-call
    arguments token-by-token, only prose."""
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]
    provider, completion = await call_llm(
        messages, key_manager, prefer=prefer, tools=tool_schema, on_event=on_event, stage=stage_name
    )
    on_event({
        "type": "model_response", "stage": stage_name, "provider": provider,
        "text": completion.content or f"[{len(completion.tool_calls)} tool call(s)]",
    })
    return provider, completion
