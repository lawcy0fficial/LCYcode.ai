import asyncio
import json

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from lcycode.api.schemas import ChatRequest, ContinueRequest, CancelRequest
from lcycode.core.agent_loop import AgentLoop
from lcycode.core.session import get_or_create
from lcycode.core import run_registry

router = APIRouter()


def _sse_pipe(coro_factory, session):
    """Shared SSE plumbing for both a fresh run and a continued one.
    Registers the run in run_registry for the duration so a separate
    /api/chat/cancel request can reach it, and always unregisters on
    the way out — success, error, or cancellation."""
    queue: asyncio.Queue = asyncio.Queue()
    cancel_event = run_registry.register(session.session_id)

    def on_event(event: dict):
        queue.put_nowait(event)

    async def run_agent():
        try:
            result = await coro_factory(on_event, cancel_event)
            queue.put_nowait({"type": "final", "data": result, "session_id": session.session_id})
        except Exception as e:  # noqa: BLE001
            queue.put_nowait({"type": "error", "message": str(e)})
        finally:
            run_registry.unregister(session.session_id)
            queue.put_nowait(None)

    async def event_stream():
        yield f"data: {json.dumps({'type': 'session', 'session_id': session.session_id})}\n\n"
        task = asyncio.create_task(run_agent())
        while True:
            event = await queue.get()
            if event is None:
                break
            yield f"data: {json.dumps(event)}\n\n"
        await task

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.post("/api/chat")
async def chat(req: ChatRequest, request: Request):
    """Starts a fresh task and, by default (routing.auto_continue in
    key.json, overridable per-request), chains chunks automatically
    until the task completes or the safety ceiling is hit — no manual
    Continue click needed for a build to run to completion. Can be
    stopped mid-run via POST /api/chat/cancel with the same session_id."""
    km = request.app.state.key_manager
    session = get_or_create(req.session_id)

    async def coro_factory(on_event, cancel_event):
        loop = AgentLoop(km, on_event=on_event, session=session,
                          auto_continue=req.auto_continue, cancel_event=cancel_event)
        return await loop.run_to_completion(req.message)

    return _sse_pipe(coro_factory, session)


@router.post("/api/chat/continue")
async def chat_continue(req: ContinueRequest, request: Request):
    """Manually resumes a paused session — used when auto_continue was
    off, or after the safety ceiling stopped an auto-chain."""
    km = request.app.state.key_manager
    session = get_or_create(req.session_id)

    if not session.has_pending:
        async def event_stream():
            yield f"data: {json.dumps({'type': 'session', 'session_id': session.session_id})}\n\n"
            yield f"data: {json.dumps({'type': 'error', 'message': 'nothing to continue — no unfinished run in this session'})}\n\n"
        return StreamingResponse(event_stream(), media_type="text/event-stream")

    pending = session.data["pending"]

    async def coro_factory(on_event, cancel_event):
        loop = AgentLoop(km, on_event=on_event, session=session,
                          auto_continue=req.auto_continue, cancel_event=cancel_event)
        result = await loop.continue_run(pending)
        # a manual continue can itself keep auto-chaining if enabled
        while (
            loop.auto_continue and not result["complete"] and not result["cancelled"]
            and result["iterations"] < loop.max_total_iterations
            and session.has_pending
        ):
            result = await loop.continue_run(session.data["pending"])
        return result

    return _sse_pipe(coro_factory, session)


@router.post("/api/chat/cancel")
async def chat_cancel(req: CancelRequest):
    """Requests cancellation of whatever run is currently in-flight for
    this session, if any. Cooperative: the loop stops at its next
    checkpoint (between stages, or after the current tool call
    finishes), not instantly — see agent_loop.py. Cancelling a session
    with nothing running is not an error, just a no-op signaled by
    was_running=False."""
    was_running = run_registry.request_cancel(req.session_id)
    return {"session_id": req.session_id, "was_running": was_running}
