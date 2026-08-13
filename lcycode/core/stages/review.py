"""REVIEW stage — judge whether the task is complete, optionally revise the plan."""
import json

from lcycode.core.prompts import ask_stage


async def run(steps, completed_log, key_manager, on_event):
    return await ask_stage(
        "REVIEW",
        f"Plan steps:\n{json.dumps(steps)}\n\n"
        f"Execution log:\n{json.dumps(completed_log[-10:])}\n\n"
        'Judge whether the overall task is now complete. Respond with JSON: '
        '{"complete": true|false, "feedback": "...", '
        '"revised_steps": [optional new/updated step list if the plan needs to change]}',
        key_manager,
        on_event,
    )
