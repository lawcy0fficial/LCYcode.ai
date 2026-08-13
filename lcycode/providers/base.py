"""Shared types for provider adapters."""

DEFAULT_TIMEOUT = 120


class ProviderError(Exception):
    """Raised when a provider adapter cannot produce a completion."""


class Completion:
    """Normalized result from any provider: either plain text content,
    or one or more native tool calls (OpenAI-compatible function-calling
    format), matching what the OpenRouter/DeepSeek/Grok APIs return."""

    def __init__(self, content=None, tool_calls=None):
        self.content = content
        self.tool_calls = tool_calls or []

    @property
    def has_tool_call(self):
        return bool(self.tool_calls)
