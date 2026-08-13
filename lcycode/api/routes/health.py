"""
health.py
A real liveness/readiness check, not just "the process is up." Checks
the things that actually determine whether this app can do anything
useful: is key.json valid, and — since Ollama is the core, always-
required provider regardless of offline_only — is it reachable.
Intended for docker-compose healthchecks, CI smoke tests, or a future
monitoring dashboard; not used internally by anything else in this
codebase.
"""
from fastapi import APIRouter, Request

from lcycode.providers import ollama
from lcycode.core import run_registry

router = APIRouter()


@router.get("/api/health")
async def health(request: Request):
    km = request.app.state.key_manager
    ollama_cfg = km.provider_config("ollama")
    host = ollama_cfg.get("host", "http://127.0.0.1:11434")
    ollama_ok = await ollama.is_reachable(host)

    healthy = ollama_ok and ollama_cfg.get("enabled", True)
    return {
        "status": "ok" if healthy else "degraded",
        "ollama_reachable": ollama_ok,
        "offline_only": km.offline_only(),
        "runs_in_flight": len(run_registry.status()),
    }
