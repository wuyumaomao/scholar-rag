"""Agent turns with process-local conversation checkpoints."""

import asyncio
from pathlib import Path
from threading import Lock

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.store.memory import InMemoryStore

from app.agent.paper_agent import AgentConversationError, AgentExecutionError
from app.agent.paper_workflow import PaperWorkflow
from app.routers import retrieval as retrieval_api


router = APIRouter(prefix="/api/agent", tags=["agent"])
# These objects live across HTTP requests; creating them inside the route
# would lose all earlier turns. This demo stores state in one process only.
checkpointer = InMemorySaver()
# Long-term demo memory is separate from graph checkpoints and must outlive
# individual PaperWorkflow instances created for each HTTP request.
memory_store = InMemoryStore()
conversation_locks: dict[str, Lock] = {}


class AgentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    file_id: str = Field(min_length=1, max_length=200)
    query: str = Field(min_length=1, max_length=2000)
    thread_id: str | None = Field(default=None, min_length=1, max_length=200)
    user_id: str = Field(default="local-user", min_length=1, max_length=200)

    @field_validator("file_id", "query", "thread_id", "user_id")
    @classmethod
    def nonblank(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not value.strip():
            raise ValueError("不能为空")
        return value.strip()


@router.post("")
async def run_agent(request: AgentRequest) -> dict:
    record = await asyncio.to_thread(retrieval_api.get_file, request.file_id)
    if record is None:
        raise HTTPException(status_code=404, detail="文件不存在")
    pdf_path = retrieval_api.UPLOAD_DIR / f"{request.file_id}.pdf"
    if not await asyncio.to_thread(Path.is_file, pdf_path):
        raise HTTPException(status_code=404, detail="PDF 文件不存在")
    agent = PaperWorkflow(settings=retrieval_api.settings,
                       retrieval_service=retrieval_api.retrieval_service,
                       checkpointer=checkpointer, conversation_locks=conversation_locks,
                       memory_store=memory_store, user_id=request.user_id)
    try:
        return await agent.run(file_id=request.file_id, pdf_path=pdf_path,
                               figure_dir=retrieval_api.FIGURE_DIR / request.file_id,
                               query=request.query, thread_id=request.thread_id)
    except AgentConversationError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except AgentExecutionError as exc:
        raise HTTPException(status_code=503, detail="Agent 执行服务当前不可用") from exc
