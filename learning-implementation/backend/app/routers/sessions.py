"""会话 API。"""

from fastapi import APIRouter, HTTPException

from app.store import get_session, list_sessions

router = APIRouter()


@router.get("/api/sessions")
async def sessions() -> list[dict[str, str]]:
    return list_sessions()


@router.get("/api/sessions/{session_id}")
async def session(session_id: str) -> dict[str, str]:
    result = get_session(session_id)
    if result is None:
        raise HTTPException(status_code=404, detail="会话不存在")
    return result
