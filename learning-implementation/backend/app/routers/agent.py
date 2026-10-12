"""A standalone single-task agent entry point for learning the graph loop."""

import asyncio
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.agent.paper_agent import AgentExecutionError, PaperAgent
from app.routers import retrieval as retrieval_api


router = APIRouter(prefix="/api/agent", tags=["agent"])


class AgentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    file_id: str = Field(min_length=1, max_length=200)
    query: str = Field(min_length=1, max_length=2000)

    @field_validator("file_id", "query")
    @classmethod
    def nonblank(cls, value: str) -> str:
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
    agent = PaperAgent(settings=retrieval_api.settings,
                       retrieval_service=retrieval_api.retrieval_service)
    try:
        return await agent.run(file_id=request.file_id, pdf_path=pdf_path,
                               figure_dir=retrieval_api.FIGURE_DIR / request.file_id,
                               query=request.query)
    except AgentExecutionError as exc:
        raise HTTPException(status_code=503, detail="Agent 执行服务当前不可用") from exc
