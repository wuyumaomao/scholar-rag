"""PDF 文件上传 API。"""

import asyncio
import os
from pathlib import Path
from typing import BinaryIO
from uuid import uuid4

from fastapi import APIRouter, File, HTTPException, Response, UploadFile, status

from app.storage.store import create_file, delete_file, get_file, list_files
from app.routers.retrieval import invalidate_retrieval_index

router = APIRouter(prefix="/api/files", tags=["files"])

UPLOAD_DIR = Path(__file__).resolve().parents[2] / "uploads"
MAX_UPLOAD_SIZE_BYTES = 50 * 1024 * 1024
UPLOAD_CHUNK_SIZE_BYTES = 1024 * 1024


class UploadTooLargeError(Exception):
    """Raised when a streamed upload exceeds the configured size limit."""


def _save_upload(source: BinaryIO, temporary_path: Path) -> int:
    """Copy the upload to a temporary file without buffering it all in memory."""
    size_bytes = 0
    with temporary_path.open("xb") as output:
        while chunk := source.read(UPLOAD_CHUNK_SIZE_BYTES):
            size_bytes += len(chunk)
            if size_bytes > MAX_UPLOAD_SIZE_BYTES:
                raise UploadTooLargeError
            output.write(chunk)
    return size_bytes


@router.post("/upload", status_code=status.HTTP_201_CREATED)
#multipart/form-data 是 HTTP 的一种请求体格式。File(...) 告诉 FastAPI：从请求的表单数据里找一个叫 file 的文件字段   
async def upload_pdf(file: UploadFile = File(...)) -> dict[str, object]:
    """Validate a PDF filename and size, then save its original bytes."""
    filename = file.filename
    if not filename or Path(filename).suffix.lower() != ".pdf":
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="仅支持 PDF 文件",
        )

    file_id = str(uuid4())
    temporary_path = UPLOAD_DIR / f".{file_id}.upload"
    destination_path = UPLOAD_DIR / f"{file_id}.pdf"

    try:#构建文件存放地址，在本文件上两级的upload下存放
        await asyncio.to_thread(UPLOAD_DIR.mkdir, parents=True, exist_ok=True)#这地方的同步函数有可能卡住，得分发出去。to_thread() 的主要作用不是加速这一次上传，而是避免阻塞事件循环
        size_bytes = await asyncio.to_thread(_save_upload, file.file, temporary_path)
        await asyncio.to_thread(os.replace, temporary_path, destination_path)
        await asyncio.to_thread(create_file, file_id, filename, size_bytes)
    except UploadTooLargeError:
        temporary_path.unlink(missing_ok=True)
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail="文件超过 50 MiB 限制",
        ) from None
    except OSError as exc:
        temporary_path.unlink(missing_ok=True)
        destination_path.unlink(missing_ok=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="文件保存失败",
        ) from exc
    except Exception as exc:
        temporary_path.unlink(missing_ok=True)
        destination_path.unlink(missing_ok=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="文件元数据保存失败",
        ) from exc
    finally:
        await file.close()

    return {
        "file_id": file_id,
        "filename": filename,
        "size_bytes": size_bytes,
        "status": "uploaded",
    }


@router.get("")
async def get_files() -> list[dict[str, object]]:
    """返回已上传文件的元数据列表。"""
    return await asyncio.to_thread(list_files)


@router.delete("/{file_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_file(file_id: str) -> Response:
    """删除文件元数据和磁盘上的原始 PDF。"""
    record = await asyncio.to_thread(get_file, file_id)
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="文件不存在")

    destination_path = UPLOAD_DIR / f"{file_id}.pdf"
    try:
        await asyncio.to_thread(destination_path.unlink, missing_ok=True)
        deleted = await asyncio.to_thread(delete_file, file_id)
        if not deleted:
            raise OSError("file metadata was not deleted")
        invalidate_retrieval_index(file_id)
    except OSError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="文件删除失败",
        ) from exc

    return Response(status_code=status.HTTP_204_NO_CONTENT)
