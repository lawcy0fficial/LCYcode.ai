#!/usr/bin/env python3
"""
verify_live.py
Runs real task(s) through the actual agent loop against your actual
Ollama daemon — no mocked providers, no test doubles. Everything else
in this project's test suite (135 backend + 20 frontend tests) runs
against fake providers, which is correct for testing orchestration
logic but means real model behavior has never been verified from the
sandbox this was built in. This script is that missing verification,
meant to be run by you, against your own Ollama, with results you can
share back for interpretation.

Usage:
    source .venv/bin/activate   # after ./setup.sh has been run once
    python3 verify_live.py                     # one simple file-write task
    python3 verify_live.py --model qwen2.5-coder:7b
    python3 verify_live.py --task "write a python fizzbuzz script to fizzbuzz.py"
    python3 verify_live.py --full              # write_file + run_shell + a
                                                 # multi-file task, one after
                                                 # another, with a summary

What it reports, per scenario/stage:
  - whether Ollama was reachable and the model responded at all
  - DESCRIBE / PLAN: did the model return valid JSON matching the
    expected schema
  - EXECUTE: did the model use NATIVE tool calling (the reliable path)
    or fall back to JSON-described tool calls (the slower, less
    reliable path) — the single most useful signal for judging
    whether your configured model is a good fit
  - REVIEW: did it correctly judge completion
  - wall-clock time per stage
  - the actual file(s) written / shell output produced, so you can
    inspect real results, not just a pass/fail

--full specifically also exercises run_shell — proving the guard in
shell_guard.py behaves correctly against a real run, not just the
mocked tests in tests/test_shell_hardening.py — and a multi-step task
to see PLAN/REVIEW behavior across more than one iteration.

Exit code is 0 if every scenario run completed, 1 otherwise — usable
in a shell conditional.
"""
import argparse
import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lcycode.config.key_manager import KeyManager
from lcycode.core.agent_loop import AgentLoop
from lcycode.core.session import Session
from lcycode.providers import ollama as ollama_provider

RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
RED = "\033[31m"
CYAN = "\033[36m"

FULL_SCENARIOS = [
    ("file write", "create a file called hello.txt containing the text 'hello from lcycode'"),
    ("shell command", "create a file called greeting.txt containing the text 'hi there', "
                       "then use a shell command to print the contents of that file"),
    ("multi-file task", "create three files named a.txt, b.txt, and c.txt, each containing "
                         "its own filename as text"),
]


def _fmt_bool(b):
    return f"{GREEN}yes{RESET}" if b else f"{RED}no{RESET}"


class Diagnostics:
    def __init__(self):
        self.stage_times = {}
        self._stage_start = {}
        self.model_responses = []
        self.tool_calls = []
        self.stage_order = []

    def on_event(self, event: dict):
        etype = event.get("type")
        now = time.monotonic()

        if etype == "stage":
            stage = event["stage"]
            if stage not in self.stage_order:
                self.stage_order.append(stage)
            self._stage_start[stage] = now

        elif etype == "model_response":
            stage = event.get("stage")
            if stage in self._stage_start:
                elapsed = now - self._stage_start[stage]
                self.stage_times.setdefault(stage, []).append(elapsed)
            preview = (event.get("text") or "")[:120].replace("\n", " ")
            self.model_responses.append((stage, event.get("provider"), preview))

        elif etype == "tool_call":
            note = event.get("note", "")
            native = "native tool call" in note
            self.tool_calls.append((event.get("tool"), native, note))

        elif etype == "tool_calling_fallback_hint":
            print(f"  {YELLOW}⚠ {event.get('message')}{RESET}")


async def run_scenario(km, name, task, max_iterations, verbose=True):
    """Runs one task through the real agent loop and returns a result
    dict — the reusable core both single-task and --full mode share."""
    km.config.setdefault("routing", {})["max_iterations"] = max_iterations
    diag = Diagnostics()
    session = Session(f"verify-live-{name.replace(' ', '-')}-{int(time.time())}")
    loop = AgentLoop(km, on_event=diag.on_event, session=session)

    if verbose:
        print(f"\n{BOLD}{CYAN}Scenario: {name}{RESET}")
        print(f"  task: {DIM}\"{task}\"{RESET}")

    t_start = time.monotonic()
    try:
        result = await loop.run(task)
        error = None
    except Exception as e:  # noqa: BLE001
        result = {"complete": False, "iterations": 0, "log": []}
        error = str(e)
    total_time = time.monotonic() - t_start

    native_count = sum(1 for _, native, _ in diag.tool_calls if native)
    fallback_count = len(diag.tool_calls) - native_count
    written_paths = [
        entry["result"]["path"] for entry in result.get("log", [])
        if entry.get("tool") in ("write_file", "edit_file", "append_file") and entry.get("result", {}).get("path")
    ]
    shell_calls = [entry for entry in result.get("log", []) if entry.get("tool") == "run_shell"]

    if verbose:
        if error:
            print(f"  {RED}exception: {error}{RESET}")
        print(f"  complete: {_fmt_bool(result['complete'])}  "
              f"iterations: {result['iterations']}/{max_iterations}  "
              f"time: {total_time:.1f}s")
        if diag.tool_calls:
            print(f"  tool calls: {len(diag.tool_calls)} "
                  f"({GREEN}{native_count} native{RESET}, "
                  f"{YELLOW if fallback_count else DIM}{fallback_count} fallback{RESET})")
        for tool, native, note in diag.tool_calls:
            tag = f"{GREEN}native{RESET}" if native else f"{YELLOW}fallback{RESET}"
            print(f"    - {tool} [{tag}]")
        for entry in shell_calls:
            r = entry.get("result", {})
            if r.get("blocked"):
                print(f"    {RED}shell command blocked: {r.get('reason')}{RESET}")
            else:
                stdout_preview = (r.get("stdout") or "").strip()[:100]
                print(f"    shell ok={r.get('ok')}: {DIM}{stdout_preview}{RESET}")
        for path in written_paths:
            print(f"    wrote: {path}")

    return {
        "name": name, "task": task, "complete": result["complete"], "error": error,
        "iterations": result["iterations"], "time": total_time,
        "native": native_count, "fallback": fallback_count,
        "written_paths": written_paths, "shell_calls": len(shell_calls),
    }


async def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--task", default=None,
                         help="a single custom task to run (default: a trivial file-write task, "
                              "ignored if --full is given)")
    parser.add_argument("--full", action="store_true",
                         help="run a fixed sequence of scenarios covering write_file, run_shell, "
                              "and a multi-step task, with a summary at the end")
    parser.add_argument("--model", default=None, help="override key.json's ollama.model for this run")
    parser.add_argument("--max-iterations", type=int, default=10,
                         help="cap per scenario (default 10, lower than production's 40 so a "
                              "struggling model doesn't run long before you see results)")
    args = parser.parse_args()

    print(f"{BOLD}{CYAN}LCYcode.ai live verification{RESET}")
    print(f"{DIM}This makes REAL calls to your Ollama daemon. Nothing here is mocked.{RESET}\n")

    km = KeyManager()
    if args.model:
        km.config["ollama"]["model"] = args.model
    model = km.provider_config("ollama").get("model")
    host = km.provider_config("ollama").get("host")

    print(f"{BOLD}Configuration{RESET}")
    print(f"  host:  {host}")
    print(f"  model: {model}")
    print(f"  offline_only: {km.offline_only()}")

    print(f"\n{BOLD}Step 1: Ollama daemon reachability{RESET}")
    t0 = time.monotonic()
    reachable = await ollama_provider.is_reachable(host)
    print(f"  reachable: {_fmt_bool(reachable)} ({time.monotonic()-t0:.2f}s)")
    if not reachable:
        print(f"\n{RED}Cannot proceed — Ollama is not reachable at {host}.{RESET}")
        print(f"{DIM}Check: is 'ollama serve' running? Does key.json's ollama.host match?{RESET}")
        return 1

    print(f"\n{BOLD}Step 2: model availability{RESET}")
    try:
        models = await ollama_provider.list_models(host)
        has_model = any(m == model or m.split(":")[0] == model.split(":")[0] for m in models)
        print(f"  '{model}' pulled locally: {_fmt_bool(has_model)}")
        if not has_model:
            print(f"  {DIM}will attempt auto-pull when the agent loop runs "
                  f"(auto_pull={km.provider_config('ollama').get('auto_pull', True)}){RESET}")
    except Exception as e:  # noqa: BLE001
        print(f"  {YELLOW}could not list models: {e}{RESET}")

    scenarios = FULL_SCENARIOS if args.full else [
        ("custom" if args.task else "file write", args.task or FULL_SCENARIOS[0][1])
    ]

    results = []
    for name, task in scenarios:
        results.append(await run_scenario(km, name, task, args.max_iterations))

    if len(results) > 1:
        print(f"\n{BOLD}{CYAN}Summary{RESET}")
        total_native = sum(r["native"] for r in results)
        total_fallback = sum(r["fallback"] for r in results)
        for r in results:
            mark = f"{GREEN}✓{RESET}" if r["complete"] else f"{RED}✗{RESET}"
            print(f"  {mark} {r['name']:20s} {r['iterations']:2d} iter, {r['time']:5.1f}s, "
                  f"{r['native']}/{r['native']+r['fallback']} native tool calls")
        print(f"\n  overall native tool-calling rate: "
              f"{total_native}/{total_native+total_fallback if (total_native+total_fallback) else 1} "
              f"({100*total_native/(total_native+total_fallback) if (total_native+total_fallback) else 0:.0f}%)")

    all_complete = all(r["complete"] for r in results)
    print()
    if all_complete:
        print(f"{GREEN}{BOLD}Verification passed — every scenario completed against your real Ollama.{RESET}")
        return 0
    else:
        print(f"{YELLOW}{BOLD}Not every scenario completed within {args.max_iterations} iterations — "
              f"diagnostic info, not necessarily a failure (some tasks genuinely need more).{RESET}")
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
