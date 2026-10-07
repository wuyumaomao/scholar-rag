"""Local semantic retrieval API."""

import asyncio
from pathlib import Path

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field, field_validator

from app.retrieval_service import RetrievalService
from app.store import get_file

router = APIRouter(prefix="/api/retrieve", tags=["retrieval"])
UPLOAD_DIR = Path(__file__).resolve().parents[2] / "uploads"
FIGURE_DIR = Path(__file__).resolve().parents[2] / "data" / "figures"
retrieval_service = RetrievalService()


def invalidate_retrieval_index(file_id: str) -> None:
    """Drop a file's cached index after the uploaded PDF is deleted."""
    retrieval_service.invalidate(file_id)


class RetrieveRequest(BaseModel):
    """Request a semantic search over one uploaded PDF."""

    file_id: str = Field(min_length=1)
    query: str = Field(min_length=1)
    top_k: int = Field(default=5, ge=1, le=50)
    child_top_k: int | None = Field(default=None, ge=1, le=200)

    @field_validator("query")
    @classmethod
    def query_must_contain_non_whitespace(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("query 不能为空")
        return value


@router.post("")
async def retrieve(request: RetrieveRequest) -> dict[str, list[dict[str, object]]]:
    """Search an uploaded PDF and return unique parent chunks."""
    record = await asyncio.to_thread(get_file, request.file_id)
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="文件不存在")

    pdf_path = UPLOAD_DIR / f"{request.file_id}.pdf"
    if not pdf_path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="PDF 文件不存在")

    try:
        hits = await asyncio.to_thread(
            retrieval_service.retrieve,
            request.file_id,
            pdf_path,
            request.query,
            FIGURE_DIR / request.file_id,
            top_k=request.top_k,
            child_top_k=request.child_top_k,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    return {
        "results": [
            {
                "chunk_id": hit.chunk.chunk_id,
                "score": hit.score,
                "context": hit.chunk.context,
                "metadata": hit.chunk.meta,
            }
            for hit in hits
        ]
    }
