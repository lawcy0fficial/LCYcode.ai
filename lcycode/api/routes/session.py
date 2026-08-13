from fastapi import APIRouter

from lcycode.core.session import Session

router = APIRouter()


@router.get("/api/session/{session_id}")
async def get_session(session_id: str):
    session = Session(session_id)
    return session.data
