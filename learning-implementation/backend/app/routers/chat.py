"""Chat API backed by document retrieval and grounded answer generation."""

import asyncio
import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field, field_validator

from app.generation.answer_generator import AnswerGenerationError, AnswerGenerator
from app.routers import retrieval as retrieval_api
from app.storage.store import add_message, create_session, get_session, touch_session

router = APIRouter()
answer_generator = AnswerGenerator(settings=retrieval_api.settings)
logger = logging.getLogger(__name__)


class ChatRequest(BaseModel):
    """Required document and question, with an optional existing session."""

    file_id: str = Field(min_length=1)
    query: str = Field(min_length=1)
    session_id: str | None = None

    @field_validator("file_id", "query")
    @classmethod
    def values_must_contain_non_whitespace(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("不能为空")
        return value


@router.post("/api/chat")
async def chat(request: ChatRequest) -> dict[str, str]:
    """Retrieve evidence, generate a grounded answer, and persist the exchange."""

    file_record = await asyncio.to_thread(retrieval_api.get_file, request.file_id)
    if file_record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="文件不存在")

    pdf_path = retrieval_api.UPLOAD_DIR / f"{request.file_id}.pdf"
    if not await asyncio.to_thread(Path.is_file, pdf_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="PDF 文件不存在"
        )

    existing_session = None
    if request.session_id is not None:
        existing_session = await asyncio.to_thread(get_session, request.session_id)
        if existing_session is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="会话不存在"
            )

    try:
        hits = await asyncio.to_thread(
            retrieval_api.retrieval_service.retrieve,
            request.file_id,
            pdf_path,
            request.query,
            retrieval_api.FIGURE_DIR / request.file_id,
            top_k=retrieval_api.settings.top_k,
            child_top_k=retrieval_api.settings.fetch_k,
            min_score=retrieval_api.settings.min_score,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc

    if hits:
        try:
            answer = await asyncio.to_thread(
                answer_generator.generate, request.query, hits
            )
        except AnswerGenerationError as exc:
            # Error messages from AnswerGenerator contain only a safe failure
            # category/status; avoid logging request headers or the full URL.
            logger.error("Answer generation failed: %s", exc)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="回答生成服务当前不可用",
            ) from exc
    else:
        answer = "我没有在这篇论文中检索到足够证据来回答这个问题。"

    if existing_session is None:
        session = await asyncio.to_thread(create_session, request.query[:50])
    else:
        session = existing_session
        await asyncio.to_thread(touch_session, session["session_id"])

    session_id = str(session["session_id"])
    await asyncio.to_thread(add_message, session_id, "user", request.query)
    await asyncio.to_thread(add_message, session_id, "assistant", answer)
    return {"answer": answer, "session_id": session_id}
