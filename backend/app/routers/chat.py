"""Chat API backed by document retrieval and grounded answer generation."""

import asyncio
import json
import logging
from pathlib import Path
from collections.abc import AsyncIterator

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, field_validator

from app.generation.answer_generator import AnswerGenerationError, AnswerGenerator
from app.retrieval.retriever import RetrievalHit
from app.routers import retrieval as retrieval_api
from app.storage.store import add_message, create_session, get_session, touch_session

router = APIRouter()
answer_generator = AnswerGenerator(settings=retrieval_api.settings)
logger = logging.getLogger(__name__)
NO_EVIDENCE_ANSWER = "我没有在这篇论文中检索到足够证据来回答这个问题。"


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


async def _prepare_chat(
    request: ChatRequest,
) -> tuple[dict[str, object] | None, list[RetrievalHit]]:
    """Validate the selected file/session and retrieve evidence before response."""
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

    return existing_session, hits


async def _persist_exchange(
    request: ChatRequest,
    existing_session: dict[str, object] | None,
    answer: str,
) -> str:
    """Persist a completed user/assistant exchange and return its session ID."""
    if existing_session is None:
        session = await asyncio.to_thread(create_session, request.query[:50])
    else:
        session = existing_session
        await asyncio.to_thread(touch_session, session["session_id"])

    session_id = str(session["session_id"])
    await asyncio.to_thread(add_message, session_id, "user", request.query)
    await asyncio.to_thread(add_message, session_id, "assistant", answer)
    return session_id


def _sse_event(event: str, data: dict[str, str]) -> str:
    """Format one SSE event with JSON data and a UTF-8-safe payload."""
    payload = json.dumps(data, ensure_ascii=False)
    return f"event: {event}\ndata: {payload}\n\n"


@router.post("/api/chat")
async def chat(request: ChatRequest) -> dict[str, str]:
    """Retrieve evidence, generate a grounded answer, and persist the exchange."""
    existing_session, hits = await _prepare_chat(request)

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
        answer = NO_EVIDENCE_ANSWER

    session_id = await _persist_exchange(request, existing_session, answer)
    return {"answer": answer, "session_id": session_id}


@router.post("/api/chat/stream")
async def stream_chat(request: ChatRequest) -> StreamingResponse:
    """Stream grounded answer text as SSE while preserving JSON chat behavior."""
    existing_session, hits = await _prepare_chat(request)

    async def generate_events() -> AsyncIterator[str]:
        answer_parts: list[str] = []
        try:
            if hits:
                async for text in answer_generator.astream(request.query, hits):
                    answer_parts.append(text)
                    yield _sse_event("token", {"text": text})
            else:
                answer_parts.append(NO_EVIDENCE_ANSWER)
                yield _sse_event("token", {"text": NO_EVIDENCE_ANSWER})

            answer = "".join(answer_parts)
            session_id = await _persist_exchange(request, existing_session, answer)
        except AnswerGenerationError as exc:
            # The exception string is already sanitized by AnswerGenerator.
            logger.error("Answer generation failed: %s", exc)
            yield _sse_event(
                "error", {"detail": "回答生成服务当前不可用"}
            )
            return
        except Exception:
            # Do not expose database, provider, or request internals to the client.
            logger.error("Chat stream failed while saving the completed exchange")
            yield _sse_event("error", {"detail": "回答保存失败，请稍后重试"})
            return

        yield _sse_event("done", {"session_id": session_id})

    return StreamingResponse(
        generate_events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
