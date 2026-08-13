"""
ws.py
A WebSocket channel as an alternative to the SSE /api/chat endpoints —
genuinely bidirectional, on one persistent connection, instead of a
one-shot POST-then-stream.

Protocol (JSON text frames both directions):
  client -> server:
    {"action": "start", "message": "...", "session_id": "...", "auto_continue": true}
    {"action": "continue", "session_id": "..."}
    {"action": "cancel", "session_id": "..."}
  server -> client:
    every agent_loop event dict — always carrying "session_id" so the
    client can route it, since a connection can have more than one
    run active at once (see below) — plus {"type": "session", ...} on
    start/continue and {"type": "error", ...} on protocol mistakes

Multiplexing: one connection can drive MULTIPLE CONCURRENT runs, one
per distinct session_id. Starting session A doesn't block starting
session B on the same socket; only starting a second run for the SAME
session while one's already active gets rejected. This matters for a
client that wants to watch/drive several sessions from one connection
(a dashboard, multiple browser tabs sharing a socket, etc.) instead of
opening N sockets or serializing everything through one.

Implementation note, because this bit is easy to get subtly wrong: a
naive "receive one message, then await the whole run before receiving
the next" loop CANNOT process a cancel sent while a run is in
progress — it isn't listening for it — and definitely can't run two
sessions at once. Receiving and running happen as concurrent tasks
sharing one outbound queue: the receiver loop always keeps listening
(so 'cancel' is processed the instant it arrives, and a second 'start'
for a different session can be accepted immediately), each run is its
own background task, and a separate sender loop drains the shared
queue to the socket. tests/test_websocket.py's cancel and multiplexing
tests specifically verify both of these — the naive version failed
both during development.
"""
import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from lcycode.core.agent_loop import AgentLoop
from lcycode.core.session import get_or_create
from lcycode.core import run_registry
from lcycode.core.logging_utils import get_logger

router = APIRouter()
log = get_logger(__name__)


@router.websocket("/ws/chat")
async def ws_chat(websocket: WebSocket):
    await websocket.accept()
    km = websocket.app.state.key_manager
    outbound: asyncio.Queue = asyncio.Queue()
    run_tasks: dict[str, asyncio.Task] = {}  # session_id -> in-flight run, for THIS connection

    async def sender():
        """Drains the shared outbound queue to the socket. Runs for the
        whole connection lifetime, independent of any single run —
        events from multiple concurrent sessions interleave through
        here, each tagged with its own session_id."""
        while True:
            event = await outbound.get()
            await websocket.send_json(event)

    def start_run(session, coro_factory):
        """Launches one run as its own background task, tagging every
        event it emits with session_id before it hits the shared
        queue — that tagging is what makes multiplexed streams
        distinguishable on the client side."""
        cancel_event = run_registry.register(session.session_id)

        def on_event(event: dict):
            outbound.put_nowait({**event, "session_id": session.session_id})

        async def _go():
            try:
                result = await coro_factory(on_event, cancel_event)
                outbound.put_nowait({"type": "final", "data": result, "session_id": session.session_id})
            except Exception as e:  # noqa: BLE001
                outbound.put_nowait({"type": "error", "message": str(e), "session_id": session.session_id})
            finally:
                run_registry.unregister(session.session_id)
                run_tasks.pop(session.session_id, None)

        run_tasks[session.session_id] = asyncio.create_task(_go())

    async def receiver():
        while True:
            msg = await websocket.receive_json()
            action = msg.get("action")

            if action == "start":
                session = get_or_create(msg.get("session_id"))
                if session.session_id in run_tasks:
                    outbound.put_nowait({
                        "type": "error", "session_id": session.session_id,
                        "message": "a run is already in progress for this session — cancel it first",
                    })
                    continue
                outbound.put_nowait({"type": "session", "session_id": session.session_id})

                async def coro_factory(on_event, cancel_event, _msg=msg, _session=session):
                    loop = AgentLoop(km, on_event=on_event, session=_session,
                                      auto_continue=_msg.get("auto_continue"), cancel_event=cancel_event)
                    return await loop.run_to_completion(_msg.get("message", ""))

                start_run(session, coro_factory)

            elif action == "continue":
                session = get_or_create(msg.get("session_id"))
                if session.session_id in run_tasks:
                    outbound.put_nowait({
                        "type": "error", "session_id": session.session_id,
                        "message": "a run is already in progress for this session — cancel it first",
                    })
                    continue
                if not session.has_pending:
                    outbound.put_nowait({
                        "type": "error", "session_id": session.session_id,
                        "message": "nothing to continue — no unfinished run in this session",
                    })
                    continue
                pending = session.data["pending"]

                async def coro_factory(on_event, cancel_event, _pending=pending, _session=session):
                    loop = AgentLoop(km, on_event=on_event, session=_session, cancel_event=cancel_event)
                    result = await loop.continue_run(_pending)
                    while (
                        loop.auto_continue and not result["complete"] and not result["cancelled"]
                        and result["iterations"] < loop.max_total_iterations and _session.has_pending
                    ):
                        result = await loop.continue_run(_session.data["pending"])
                    return result

                start_run(session, coro_factory)

            elif action == "cancel":
                target = msg.get("session_id")
                was_running = run_registry.request_cancel(target) if target else False
                outbound.put_nowait({"type": "cancel_ack", "session_id": target, "was_running": was_running})

            else:
                outbound.put_nowait({"type": "error", "message": f"unknown action: {action!r}"})

    sender_task = asyncio.create_task(sender())
    receiver_task = asyncio.create_task(receiver())
    try:
        done, _pending = await asyncio.wait(
            {sender_task, receiver_task}, return_when=asyncio.FIRST_EXCEPTION
        )
        for t in done:
            t.result()  # re-raise, if either task died unexpectedly (e.g. disconnect)
    except WebSocketDisconnect:
        log.info("websocket client disconnected (%d run(s) still in flight)", len(run_tasks))
    finally:
        sender_task.cancel()
        receiver_task.cancel()
        for session_id, task in list(run_tasks.items()):
            run_registry.request_cancel(session_id)
            if not task.done():
                task.cancel()
