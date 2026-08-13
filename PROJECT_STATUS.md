# Project status

A single, honest snapshot of where LCYcode.ai stands. Written at the
end of a long build — meant to be read once, top to bottom, by anyone
picking this project up fresh. Everything stated here was actually
verified (see "How this was verified" below), not just asserted.

## What this is

An offline-first agentic coding agent. Ollama runs every stage of the
loop (Describe → Plan → Execute → Review) by default — free, unlimited,
no login, enforced at the router level (`offline_only: true`), not
just a preference that degrades. Cloud fallback (OpenRouter, DeepSeek,
Grok) is optional and off by default; placeholder keys are filtered so
they can never accidentally reach a real endpoint. There is
deliberately no Anthropic API integration anywhere in this codebase —
if you want Claude Code itself, `setup-claude-code.sh` runs the real
CLI against the same local Ollama, also free, also no login.

## What's built

- **Core loop**: resumable in bounded chunks, auto-chained across
  chunks up to a real safety ceiling, cooperatively cancellable
  (GUI Stop button, CLI Ctrl-C, `POST /api/chat/cancel`, or a WebSocket
  frame — all one mechanism).
- **Interfaces**: GUI (chat + live pipeline rail + real diff view),
  CLI, SSE API, and a genuinely bidirectional WebSocket supporting
  multiple concurrent sessions on one connection.
- **15 tools**, all workspace-sandboxed: filesystem, `run_shell`
  (guarded — see below), search, git, test/lint runners. Every
  file-mutating call captures a real before/after diff.
- **Safety layers**: config validation, structured logging,
  retry/backoff, session log/text compaction on long chains (measured
  66% size reduction), and a pattern-based guard on `run_shell`
  (workspace escape, destructive deletes, privilege escalation, fork
  bombs, etc.) plus best-effort resource limits.
- **Diagnostics**: `verify_live.py` — runs real task(s) through the
  real loop against your real Ollama, reports native-vs-fallback
  tool-calling behavior, per-stage timing, actual output. `--full`
  exercises `run_shell` and a multi-step task too.

## What's tested, and how

**137 backend tests + 20 frontend tests**, all passing, stress-tested
(20+ consecutive full-suite runs with zero failures — this project hit
real flakiness twice during development, from asyncio scheduling
fairness issues under a zero-latency test double; both were root-caused
and fixed, not papered over, and both fixes are explained in the tests
themselves).

Every one of those tests runs against **mocked providers** — fake
`call_llm` functions returning canned `Completion` objects, not a real
model. That's the right tool for testing this project's own
orchestration logic (the loop, cancellation, sessions, diffing, the
guard, the WebSocket concurrency) and it's been enough to catch real
bugs: a word-boundary regex mistake in the shell guard, a genuine race
condition in the first WebSocket implementation, `run_shell` blocking
the entire event loop via a synchronous subprocess call. All caught by
tests, not by inspection, and all fixed with the fix itself verified
by a follow-up test or a live end-to-end proof.

## What's honestly NOT verified

- **Real Ollama model behavior.** No test in this project has ever
  talked to an actual running Ollama daemon. `verify_live.py` exists
  specifically because of this gap — it's built and its own logic is
  verified (against a fake-but-real HTTP server standing in for
  Ollama's API shape), but running it against your actual Ollama is
  something only you can do from here.
- **The Docker build itself.** No Docker available in the sandbox this
  was built in. The `Dockerfile`/`docker-compose.yml` are syntactically
  valid and the healthcheck command is verified against a real running
  server in both directions (healthy/degraded), but `docker build` has
  never actually been run.
- **Real cloud provider behavior.** OpenRouter/DeepSeek/Grok are wired
  in with the same pattern as Ollama, but since they're off by default
  and this sandbox has no real API keys for them, none of the three
  has ever made a real request either.

## How this was verified (the standard applied throughout)

Every claim of "this works" in this project's history was backed by
one of: a passing automated test exercising the real code path, a
live end-to-end run against a mocked-but-realistic HTTP server (not
just calling a Python function directly), or an explicit statement
that it *wasn't* verified when it genuinely couldn't be from this
sandbox. Repackaging always included a clean-room check: extract the
actual zip being delivered into a fresh directory, install from
scratch, run the full test suite there — not just in the working
directory that had already been fiddled with.

## If you're picking this up next

Read the "Honest caveats / good next steps" section of `README.md`
for the current list. As of this document, real-world model behavior
(via `verify_live.py`) is the most valuable thing that could happen
next — and it's the one thing that requires you, not more building
from this side.
