"""
main.py (CLI)
Claude-Code-style terminal chat. No login, no account — reads
key.json, runs the DESCRIBE -> PLAN -> EXECUTE -> REVIEW loop, and
prints stage transitions and tool calls live.

Ctrl-C during an active run requests a cooperative cancel (same
mechanism as the GUI's Stop button / POST /api/chat/cancel) instead of
crashing the process — the loop stops at its next checkpoint and the
partial result is checkpointed to the session, resumable with
'continue' just like a paused run. Ctrl-C at the prompt (nothing
running) still exits normally.
"""
import asyncio
import signal

from lcycode.config.key_manager import KeyManager
from lcycode.core.agent_loop import AgentLoop
from lcycode.core.session import get_or_create
from lcycode.cli.ui import BANNER, DIM, CYAN, GREEN, YELLOW, RESET, render_event


async def _run_cancellable(coro_awaitable, cancel_event):
    """Installs a SIGINT handler that sets cancel_event instead of
    raising KeyboardInterrupt, for the duration of one run — restores
    the default handler afterward so Ctrl-C at the prompt behaves
    normally again."""
    def handle_sigint(signum, frame):
        print(f"\n{YELLOW}stopping at the next checkpoint...{RESET}")
        cancel_event.set()

    try:
        old_handler = signal.signal(signal.SIGINT, handle_sigint)
    except (ValueError, AttributeError):
        old_handler = None  # not the main thread, or no SIGINT on this platform

    try:
        return await coro_awaitable
    finally:
        if old_handler is not None:
            signal.signal(signal.SIGINT, old_handler)


async def run():
    print(BANNER)
    km = KeyManager()
    session = get_or_create()  # one session per CLI run, so turns share context
    print(f"{DIM}keys loaded from key.json — routing order: "
          f"{km.routing().get('order')}{RESET}")
    print(f"{DIM}session: {session.session_id}{RESET}")
    print(f"{DIM}type 'continue' to resume an unfinished build, 'exit' to quit, "
          f"Ctrl-C to stop a run in progress{RESET}\n")

    while True:
        try:
            task = input(f"{CYAN}lcycode>{RESET} ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not task:
            continue
        if task in ("exit", "quit"):
            break

        cancel_event = asyncio.Event()
        loop = AgentLoop(km, on_event=render_event, session=session, cancel_event=cancel_event)

        if task.lower() == "continue":
            if not session.has_pending:
                print(f"{YELLOW}nothing to continue — no unfinished run in this session.{RESET}\n")
                continue

            async def _continue_chain():
                result = await loop.continue_run(session.data["pending"])
                while (loop.auto_continue and not result["complete"] and not result["cancelled"]
                       and result["iterations"] < loop.max_total_iterations and session.has_pending):
                    result = await loop.continue_run(session.data["pending"])
                return result

            result = await _run_cancellable(_continue_chain(), cancel_event)
        else:
            result = await _run_cancellable(loop.run_to_completion(task), cancel_event)

        if result["complete"]:
            print(f"\n{GREEN}done in {result['iterations']} iteration(s).{RESET}\n")
        elif result["cancelled"]:
            print(f"\n{YELLOW}stopped after {result['iterations']} iteration(s) — "
                  f"progress saved, type 'continue' to resume.{RESET}\n")
        else:
            print(f"\n{YELLOW}paused after {result['iterations']} iteration(s) "
                  f"(hit the iteration cap) — type 'continue' to keep going.{RESET}\n")


def main():
    asyncio.run(run())


if __name__ == "__main__":
    main()
