"""聊天 API。"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.store import add_message, create_session, get_session, touch_session

router = APIRouter()


class ChatRequest(BaseModel):
    """聊天请求体。"""

    query: str
    session_id: str | None = None


@router.post("/api/chat")
async def chat(request: ChatRequest) -> dict[str, str]:
    """返回固定回答，并创建或复用会话。"""

    if request.session_id is None:
        session = create_session(title=request.query[:50])
    else:
        session = get_session(request.session_id)
        if session is None:
            raise HTTPException(status_code=404, detail="会话不存在")
        touch_session(request.session_id)

    answer = f"收到你的问题：{request.query}"
    add_message(session["session_id"], "user", request.query)
    add_message(session["session_id"], "assistant", answer)
    return {
        "answer": answer,
        "session_id": session["session_id"],
    }
