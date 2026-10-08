"""会话 API。"""

from fastapi import APIRouter, HTTPException, Response, status

from app.storage.store import delete_session, get_session, list_messages, list_sessions

router = APIRouter()


@router.get("/api/sessions")
async def sessions() -> list[dict[str, object]]:
    return list_sessions()


@router.get("/api/sessions/{session_id}")
async def session(session_id: str) -> dict[str, object]:
    result = get_session(session_id)
    if result is None:
        raise HTTPException(status_code=404, detail="会话不存在")
    return {
        "session_id": result["session_id"],
        "title": result["title"],
        "created_at": result["created_at"],
        "updated_at": result["updated_at"],
    }


@router.get("/api/sessions/{session_id}/history")
async def session_history(session_id: str) -> list[dict[str, str]]:
    result = get_session(session_id)
    if result is None:
        raise HTTPException(status_code=404, detail="会话不存在")
    return list_messages(session_id)


@router.delete("/api/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_session(session_id: str) -> Response:
    if not delete_session(session_id):
        raise HTTPException(status_code=404, detail="会话不存在")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
