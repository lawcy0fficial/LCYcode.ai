"""PLAN stage — break the described task into ordered, concrete steps."""
import json

from lcycode.core.prompts import ask_stage


async def run(description, key_manager, on_event):
    return await ask_stage(
        "PLAN",
        f"Task summary: {json.dumps(description)}\n\n"
        'Break this into an ordered list of concrete steps. Respond with JSON: '
        '{"steps": [{"id": 1, "title": "...", "detail": "..."}]}',
        key_manager,
        on_event,
    )
