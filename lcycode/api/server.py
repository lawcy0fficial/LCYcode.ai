"""
server.py
FastAPI app factory for LCYcode.ai. Routes live in lcycode/api/routes/*
and are included here; the GUI is served straight from frontend/.
"""
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from lcycode.config.key_manager import KeyManager
from lcycode.config.settings import FRONTEND_DIR
from lcycode.api.routes import chat, status, workspace, session, sessions, health, ws


def create_app() -> FastAPI:
    app = FastAPI(title="LCYcode.ai")
    app.state.key_manager = KeyManager()

    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")
    app.include_router(chat.router)
    app.include_router(status.router)
    app.include_router(workspace.router)
    app.include_router(session.router)
    app.include_router(sessions.router)
    app.include_router(health.router)
    app.include_router(ws.router)

    @app.get("/", response_class=HTMLResponse)
    async def index():
        return (FRONTEND_DIR / "index.html").read_text()

    return app


app = create_app()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8420)
