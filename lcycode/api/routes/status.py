from fastapi import APIRouter, Request

from lcycode.providers import ollama

router = APIRouter()


@router.get("/api/status")
async def status(request: Request):
    km = request.app.state.key_manager
    out = km.status()
    out["offline_only"] = km.offline_only()

    ollama_cfg = km.provider_config("ollama")
    host = ollama_cfg.get("host", "http://127.0.0.1:11434")
    out["ollama"]["reachable"] = await ollama.is_reachable(host)
    return out


@router.get("/api/ollama/models")
async def ollama_models(request: Request):
    km = request.app.state.key_manager
    host = km.provider_config("ollama").get("host", "http://127.0.0.1:11434")
    try:
        return {"ok": True, "models": await ollama.list_models(host)}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)}
