"""Terminal rendering helpers for the CLI front end."""

RESET = "\033[0m"
DIM = "\033[2m"
CYAN = "\033[36m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
MAGENTA = "\033[35m"
RED = "\033[31m"

STAGE_COLORS = {
    "DESCRIBE": CYAN,
    "PLAN": MAGENTA,
    "EXECUTE": YELLOW,
    "REVIEW": GREEN,
    "RESUME": MAGENTA,
    "PAUSED": YELLOW,
    "DONE": GREEN,
}

BANNER = r"""
  _      _____ __     __            _
 | |    / ____|\ \   / /           | |
 | |   | |      \ \_/ /___ ___   __| | ___
 | |   | |       \   // __/ _ \ / _` |/ _ \
 | |___| |____    | || (_| (_) | (_| |  __/
 |______\_____|   |_| \___\___/ \__,_|\___|

  offline-first agentic coding agent — no login required
"""


def render_event(event: dict):
    etype = event.get("type")
    if etype == "stage":
        stage = event["stage"]
        color = STAGE_COLORS.get(stage, RESET)
        print(f"\n{color}▶ {stage}{RESET}")
    elif etype == "token":
        print(f"{DIM}{event.get('delta', '')}{RESET}", end="", flush=True)
    elif etype == "model_response":
        tag = GREEN if event.get("provider") == "ollama" else YELLOW
        print(f"\n  {DIM}[{tag}{event.get('provider')}{RESET}{DIM}]{RESET}")
    elif etype == "describe_result":
        print(f"{DIM}{event['data'].get('summary', '')}{RESET}")
    elif etype == "plan_result":
        for step in event["data"].get("steps", []):
            print(f"  {DIM}{step.get('id')}. {step.get('title')}{RESET}")
    elif etype == "tool_call":
        print(f"  {YELLOW}⚙ {event.get('tool')}{RESET}  {event.get('note', '')}")
    elif etype == "tool_result":
        result = event.get("result", {})
        ok = result.get("ok", True)
        mark = f"{GREEN}✓{RESET}" if ok else f"{RED}✗{RESET}"
        print(f"    {mark} {result}")
    elif etype == "review_result":
        fb = event["data"].get("feedback", "")
        if fb:
            print(f"  {DIM}review: {fb}{RESET}")
    elif etype == "auto_continue":
        print(f"  {DIM}↻ auto-continuing ({event.get('iterations_so_far')}/"
              f"{event.get('ceiling')} iterations so far)...{RESET}")
    elif etype == "auto_continue_ceiling_hit":
        print(f"  {RED}safety ceiling reached at {event.get('iterations')} iterations "
              f"without completing — stopping.{RESET}")
    elif etype == "tool_calling_fallback_hint":
        print(f"  {YELLOW}⚠ {event.get('message')}{RESET}")
    elif etype == "error":
        print(f"{RED}error: {event.get('message')}{RESET}")
