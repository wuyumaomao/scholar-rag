"""Agent turns with process-local conversation checkpoints."""

import asyncio
from pathlib import Path
from threading import Lock

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.agent.paper_agent import AgentConversationError, AgentExecutionError
from app.agent.paper_workflow import PaperWorkflow
from app.routers import retrieval as retrieval_api
from app.storage.store import list_files


router = APIRouter(prefix="/api/agent", tags=["agent"])
# These objects live across HTTP requests; creating them inside the route
# would lose all earlier turns. This demo stores state in one process only.
# Initialized and closed by app.main lifespan, never silently fall back to RAM.
checkpointer = None
memory_store = None
conversation_locks: dict[str, Lock] = {}


class AgentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scope: str = Field(default="paper", pattern="^(paper|corpus)$")
    file_id: str | None = Field(default=None, min_length=1, max_length=200)
    query: str = Field(min_length=1, max_length=2000)
    thread_id: str | None = Field(default=None, min_length=1, max_length=200)
    user_id: str = Field(default="local-user", min_length=1, max_length=200)

    @model_validator(mode="after")
    def validate_scope(self):
        if self.scope == "paper" and not self.file_id:
            raise ValueError("paper scope 必须提供 file_id")
        if self.scope == "corpus" and self.file_id is not None:
            raise ValueError("corpus scope 不应提供 file_id")
        return self

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
    if checkpointer is None or memory_store is None:
        raise HTTPException(status_code=503, detail="Agent 持久化存储尚未初始化")
    corpus_files = None
    pdf_path = figure_dir = None
    if request.scope == "paper":
        record = await asyncio.to_thread(retrieval_api.get_file, request.file_id)
        if record is None:
            raise HTTPException(status_code=404, detail="文件不存在")
        pdf_path = retrieval_api.UPLOAD_DIR / f"{request.file_id}.pdf"
        figure_dir = retrieval_api.FIGURE_DIR / request.file_id
        if not await asyncio.to_thread(Path.is_file, pdf_path):
            raise HTTPException(status_code=404, detail="PDF 文件不存在")
    else:
        records = await asyncio.to_thread(list_files)
        corpus_files = []
        for record in records:
            candidate_id = str(record["file_id"])
            candidate_pdf = retrieval_api.UPLOAD_DIR / f"{candidate_id}.pdf"
            if await asyncio.to_thread(Path.is_file, candidate_pdf):
                corpus_files.append((candidate_id, candidate_pdf,
                                     retrieval_api.FIGURE_DIR / candidate_id))
        if not corpus_files:
            raise HTTPException(status_code=404, detail="论文库为空")
    agent = PaperWorkflow(settings=retrieval_api.settings,
                       retrieval_service=retrieval_api.retrieval_service,
                       checkpointer=checkpointer, conversation_locks=conversation_locks,
                       memory_store=memory_store, user_id=request.user_id)
    try:
        return await agent.run(file_id=request.file_id, pdf_path=pdf_path,
                               figure_dir=figure_dir, corpus_files=corpus_files,
                               scope=request.scope, query=request.query,
                               thread_id=request.thread_id)
    except AgentConversationError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except AgentExecutionError as exc:
        raise HTTPException(status_code=503, detail="Agent 执行服务当前不可用") from exc
