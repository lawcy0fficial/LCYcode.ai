"""DESCRIBE stage — restate the user's task as a structured summary."""
from lcycode.core.prompts import ask_stage


async def run(user_task, key_manager, on_event, history_context=""):
    context_block = f"{history_context}\n\n" if history_context else ""
    return await ask_stage(
        "DESCRIBE",
        f"{context_block}"
        f'Task from the user: "{user_task}"\n\n'
        'Respond with JSON: {"summary": "...", "goals": ["..."], '
        '"assumptions": ["..."]}',
        key_manager,
        on_event,
    )
