"""Local semantic retrieval API."""

import asyncio
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.config import Settings
from app.retrieval_filters import RetrievalFilters
from app.retrieval_service import RetrievalService
from app.store import get_file

router = APIRouter(prefix="/api/retrieve", tags=["retrieval"])
UPLOAD_DIR = Path(__file__).resolve().parents[2] / "uploads"
FIGURE_DIR = Path(__file__).resolve().parents[2] / "data" / "figures"
settings = Settings.from_env()
retrieval_service = RetrievalService(settings=settings)


def invalidate_retrieval_index(file_id: str) -> None:
    """Drop a file's cached index after the uploaded PDF is deleted."""
    retrieval_service.invalidate(file_id)


ElementType = Literal[
    "section_header",
    "paragraph",
    "list_item",
    "figure",
    "table",
    "formula",
    "caption",
    "footnote",
    "unknown",
]


class MetadataFilterRequest(BaseModel):
    """Optional metadata constraints applied before child ranking."""

    model_config = ConfigDict(extra="forbid")

    element_types: list[ElementType] = Field(default_factory=list, max_length=9)
    page_from: int | None = Field(default=None, ge=1)
    page_to: int | None = Field(default=None, ge=1)
    section_path_prefix: list[str] = Field(default_factory=list, max_length=12)

    @field_validator("element_types", "section_path_prefix")
    @classmethod
    def values_must_be_nonempty(cls, values: list[str]) -> list[str]:
        if any(not value.strip() for value in values):
            raise ValueError("列表值不能为空")
        return values

    @model_validator(mode="after")
    def page_range_must_be_ordered(self) -> "MetadataFilterRequest":
        if (
            self.page_from is not None
            and self.page_to is not None
            and self.page_from > self.page_to
        ):
            raise ValueError("page_from 不能大于 page_to")
        return self

    def to_filters(self) -> RetrievalFilters:
        return RetrievalFilters(
            element_types=tuple(self.element_types),
            page_from=self.page_from,
            page_to=self.page_to,
            section_path_prefix=tuple(self.section_path_prefix),
        )


class RetrieveRequest(BaseModel):
    """Request a semantic search over one uploaded PDF."""

    file_id: str = Field(min_length=1)
    query: str = Field(min_length=1)
    top_k: int = Field(default=settings.top_k, ge=1, le=50)
    child_top_k: int = Field(default=settings.fetch_k, ge=1, le=200)
    min_score: float = Field(default=settings.min_score, ge=-1, le=1)
    use_hyde: bool = False
    filters: MetadataFilterRequest = Field(default_factory=MetadataFilterRequest)

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
            min_score=request.min_score,
            use_hyde=request.use_hyde,
            filters=request.filters.to_filters(),
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
