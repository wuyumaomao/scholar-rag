"""聊天 API。"""

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()


class ChatRequest(BaseModel):
    """聊天请求体。"""

    query: str


@router.post("/api/chat")
async def chat(request: ChatRequest) -> dict[str, str]:
    """返回固定回答，暂时不接入 LLM。"""

    return {"answer": f"收到你的问题：{request.query}"}
