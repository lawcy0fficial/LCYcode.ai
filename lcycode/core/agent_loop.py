"""
agent_loop.py
Orchestrates the DESCRIBE -> PLAN -> EXECUTE -> REVIEW cycle by
calling out to the four stage modules in lcycode.core.stages, and
dispatching tool calls through lcycode.tools.registry.

The EXECUTE/REVIEW cycle is capped at `max_iterations` per chunk for
safety (a bad model/key combo can't loop forever on one call), but the
loop is resumable: if the reviewer hasn't marked the task complete
when a chunk's cap is hit, the unfinished state (steps + execution
log) is saved on the session. `continue_run()` picks up exactly where
a chunk left off — no re-describing, no re-planning, no repeated work.

`run_to_completion()` is the "endless code" bridge itself: when
`routing.auto_continue` is on (the default), it chains chunks
automatically — pause, save, resume, pause, save, resume — with no
human click in between, up to `routing.max_total_iterations` as a hard
safety ceiling (default 1000; a real stop, not a cost limit, since
local Ollama calls are free — it exists purely so a model stuck never
saying "complete" can't loop forever unnoticed). If that ceiling is
hit without completion, the run stops and surfaces normally so a human
can look at it — the GUI's Continue button still works from there too.

Cancellation is cooperative via an optional asyncio.Event (see
run_registry.py): checked between stages and between EXECUTE/REVIEW
iterations, never mid-tool-call — a tool already running finishes,
the loop just doesn't start another one. A cancelled run is treated
like any other pause: state is checkpointed to the session so it can
still be resumed later if that's what's wanted, it's just distinctly
tagged so the GUI/CLI can tell "you stopped it" from "it hit the cap."

`on_event(event: dict)` fires at every stage transition, tool call,
and model response — the API layer turns this into an SSE or
WebSocket stream for the GUI's live coding view; the CLI turns it
into colored terminal output. Same loop, multiple front ends.
"""
import asyncio

from lcycode.core.stages import describe, plan, execute, review
from lcycode.core.logging_utils import get_logger
from lcycode.tools import registry

log = get_logger(__name__)


class AgentLoop:
    def __init__(self, key_manager, on_event=None, session=None, auto_continue=None, cancel_event=None):
        self.km = key_manager
        self.on_event = on_event or (lambda e: None)
        routing = key_manager.routing()
        self.max_iterations = routing.get("max_iterations", 40)
        self.max_total_iterations = routing.get("max_total_iterations", 1000)
        # explicit auto_continue arg overrides key.json for this one run
        # (e.g. a GUI toggle), otherwise fall back to the configured default.
        self.auto_continue = routing.get("auto_continue", True) if auto_continue is None else auto_continue
        self.session = session
        self.cancel_event = cancel_event

    def _emit(self, event_type, **data):
        self.on_event({"type": event_type, **data})

    def _cancelled(self) -> bool:
        return bool(self.cancel_event and self.cancel_event.is_set())

    async def _yield_to_scheduler(self):
        """A deliberate scheduler yield at every cancellation checkpoint.

        Without this, cancellation responsiveness depends entirely on
        incidental suspension points elsewhere (a real network call to
        a provider, asyncio.to_thread dispatching a tool call) — fine
        with real I/O, since even a fast local Ollama response takes
        real wall-clock time. But if a tool call's work is trivial
        (e.g. a fast local file write) and completes almost instantly,
        its task can keep re-queuing itself onto asyncio's ready queue
        fast enough to noticeably delay a concurrently-waiting task
        (like the WebSocket receiver processing an incoming cancel)
        getting its turn — observed directly while stress-testing
        tests/test_websocket.py's cancellation test, where a cancel
        sent after 2 tool calls sometimes didn't take effect until 25+
        iterations later. That's not a correctness bug (cancellation
        still lands eventually — it's cooperative, not instant, by
        design), but relying on incidental yields to make it *prompt*
        was the wrong thing to depend on. This makes fairness explicit
        instead of coincidental."""
        await asyncio.sleep(0)

    async def _execute_review_cycle(self, steps, completed_log, start_iteration=0):
        """Runs up to max_iterations of EXECUTE -> REVIEW starting from
        whatever state is passed in. Returns (steps, completed_log,
        iterations_run, complete, cancelled)."""
        iteration = 0
        complete = False
        cancelled = False
        while iteration < self.max_iterations:
            await self._yield_to_scheduler()
            if self._cancelled():
                cancelled = True
                log.info("cancellation observed before iteration %d", start_iteration + iteration + 1)
                break

            iteration += 1
            self._emit("stage", stage="EXECUTE", iteration=start_iteration + iteration)

            execution = await execute.run(steps, completed_log, self.km, self.on_event)
            if execution.get("done"):
                complete = True
                break

            tool_name = execution.get("tool")
            args = execution.get("args", {})
            note = execution.get("note", "")
            self._emit("tool_call", tool=tool_name, args=args, note=note)
            log.info("tool_call tool=%s args=%s", tool_name,
                     {k: v for k, v in args.items() if k != "content"})

            try:
                result = await registry.execute(tool_name, args)
            except Exception as e:  # noqa: BLE001
                result = {"ok": False, "error": str(e)}
                log.warning("tool_call failed tool=%s error=%s", tool_name, e)

            self._emit("tool_result", tool=tool_name, result=result)
            completed_log.append(
                {"step_id": execution.get("step_id"), "tool": tool_name,
                 "args": args, "result": result}
            )

            await self._yield_to_scheduler()
            if self._cancelled():
                cancelled = True
                log.info("cancellation observed after tool call, before REVIEW")
                break

            self._emit("stage", stage="REVIEW", iteration=start_iteration + iteration)
            review_result = await review.run(steps, completed_log, self.km, self.on_event)
            self._emit("review_result", data=review_result)

            if review_result.get("revised_steps"):
                steps = review_result["revised_steps"]
            if review_result.get("complete"):
                complete = True
                break

        return steps, completed_log, iteration, complete, cancelled

    def _finish(self, user_task, description, steps, completed_log, iterations, complete, cancelled=False):
        stage = "DONE" if complete else ("CANCELLED" if cancelled else "PAUSED")
        self._emit("stage", stage=stage, iterations=iterations, complete=complete, cancelled=cancelled)
        log.info("stage=%s iterations=%d tool_calls=%d complete=%s cancelled=%s",
                  stage, iterations, len(completed_log), complete, cancelled)
        result = {
            "description": description,
            "steps": steps,
            "log": completed_log,
            "iterations": iterations,
            "complete": complete,
            "cancelled": cancelled,
        }
        if self.session:
            if complete:
                self.session.clear_pending()
            else:
                # cancelled or capped — either way, checkpoint so it's resumable
                self.session.set_pending(user_task, description, steps, completed_log)
            self.session.add_turn(user_task, result)
        return result

    async def run(self, user_task: str):
        history_context = self.session.history_context() if self.session else ""

        if self._cancelled():
            return self._finish(user_task, {}, [], [], 0, False, cancelled=True)

        self._emit("stage", stage="DESCRIBE")
        log.info("stage=DESCRIBE task=%r", user_task)
        description = await describe.run(user_task, self.km, self.on_event, history_context)
        self._emit("describe_result", data=description)

        if self._cancelled():
            return self._finish(user_task, description, [], [], 0, False, cancelled=True)

        self._emit("stage", stage="PLAN")
        plan_result = await plan.run(description, self.km, self.on_event)
        steps = plan_result.get("steps", [])
        self._emit("plan_result", data=plan_result)

        steps, completed_log, iterations, complete, cancelled = await self._execute_review_cycle(steps, [])
        return self._finish(user_task, description, steps, completed_log, iterations, complete, cancelled)

    async def continue_run(self, pending: dict):
        """Resumes an unfinished run from saved session state — no
        DESCRIBE/PLAN repeated, straight back into EXECUTE/REVIEW."""
        user_task = pending["user_task"]
        description = pending["description"]
        steps = pending["steps"]
        completed_log = pending["log"]
        prior_iterations = pending.get("iterations", 0)

        if self._cancelled():
            return self._finish(user_task, description, steps, completed_log, prior_iterations, False, cancelled=True)

        self._emit("stage", stage="RESUME", prior_iterations=prior_iterations)
        log.info("stage=RESUME task=%r prior_iterations=%d", user_task, prior_iterations)

        steps, completed_log, iterations, complete, cancelled = await self._execute_review_cycle(
            steps, completed_log, start_iteration=prior_iterations
        )
        total_iterations = prior_iterations + iterations
        return self._finish(user_task, description, steps, completed_log, total_iterations, complete, cancelled)

    async def run_to_completion(self, user_task: str):
        """The endless-building entry point: runs the first chunk, then
        — if auto_continue is on — keeps chaining continue_run() chunks
        with no human interaction until the task completes, is
        cancelled, or hits max_total_iterations. Every chunk still
        checkpoints to the session, so a crash (or a cancel) mid-chain
        loses at most one chunk."""
        result = await self.run(user_task)
        while (
            self.auto_continue
            and not result["complete"]
            and not result["cancelled"]
            and result["iterations"] < self.max_total_iterations
            and self.session
            and self.session.has_pending
        ):
            self._emit("auto_continue", iterations_so_far=result["iterations"],
                       ceiling=self.max_total_iterations)
            log.info("auto_continue: chaining next chunk at %d/%d iterations",
                      result["iterations"], self.max_total_iterations)
            result = await self.continue_run(self.session.data["pending"])

        if not result["complete"] and not result["cancelled"] and result["iterations"] >= self.max_total_iterations:
            self._emit("auto_continue_ceiling_hit", iterations=result["iterations"])
            log.warning("hit max_total_iterations (%d) without completing task %r",
                        self.max_total_iterations, user_task)
        return result
