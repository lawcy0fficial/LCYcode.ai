"""
model_capabilities.py
A small, honest registry of which locally-runnable coding models are
known to handle native OpenAI-style tool calling reliably. This isn't
exhaustive — Ollama adds tool-call support to more models over time —
but it catches the common case: a very small general-purpose model
that will mostly ignore the tools schema and talk in prose instead,
which pushes the EXECUTE stage into its (slower, less reliable) JSON
fallback path on every step.

Used by setup.sh (a plain-text lookup, see the __main__ block) and
importable from Python for the same check at runtime.
"""

# name -> "good" | "limited" | "unknown"
KNOWN_TOOL_CALLING_SUPPORT = {
    "qwen3-coder": "good",           # Ollama's own official example model for this integration
    "qwen2.5-coder": "good",
    "qwen2.5": "good",
    "qwen2": "limited",
    "glm-4.7-flash": "good",          # tool-calling tuned, 128K context — well-suited to this loop
    "llama3.1": "good",
    "llama3.2": "good",
    "llama3": "limited",
    "mistral-nemo": "good",
    "mistral": "limited",
    "deepseek-coder-v2": "good",
    "deepseek-coder": "limited",   # the default demo model — small, general JSON works, tool-calls are hit-or-miss
    "deepseek-r1": "limited",       # reasoning-tuned, not tool-call-tuned
    "codellama": "limited",
    "phi3": "limited",
    "gemma2": "limited",
    "tinyllama": "limited",
    "gpt-oss": "unknown",            # commonly pulled for this use case but tool-calling
                                       # quality wasn't confirmed in any source checked for this
}

RECOMMENDED_TOOL_CALLING_MODELS = [
    "qwen3-coder",
    "qwen2.5-coder:7b",
    "qwen2.5-coder:14b",
    "glm-4.7-flash",
    "llama3.1:8b",
]

# Independent of tool-calling quality: Ollama's own docs recommend at
# least 32K tokens of context for Claude Code (and, by the same logic,
# any long agentic loop like this one) to work well — a model running
# at a small default context window will truncate the conversation and
# can produce confused or hallucinated output that looks like a model
# quality problem but is actually a context-window problem. Worth
# checking `ollama show <model>` for the context length your model is
# actually configured with if behavior seems off.
RECOMMENDED_MIN_CONTEXT_TOKENS = 32000


def lookup(model_name: str) -> str:
    """model_name like 'deepseek-coder:1.3b' -> 'good' | 'limited' | 'unknown'."""
    base = model_name.split(":")[0].lower()
    return KNOWN_TOOL_CALLING_SUPPORT.get(base, "unknown")


if __name__ == "__main__":
    # invoked from setup.sh as: python3 -m lcycode.config.model_capabilities <model>
    import sys
    if len(sys.argv) > 1:
        print(lookup(sys.argv[1]))
