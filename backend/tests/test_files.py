"""文件上传与元数据 API 的行为测试。"""

from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from app.routers import files


client = TestClient(app)


def test_upload_list_and_delete_file(monkeypatch, tmp_path: Path) -> None:
    records: dict[str, dict[str, object]] = {}

    def create_file(file_id: str, filename: str, size_bytes: int) -> dict[str, object]:
        record = {
            "file_id": file_id,
            "filename": filename,
            "size_bytes": size_bytes,
            "created_at": 100.0,
        }
        records[file_id] = record
        return record

    monkeypatch.setattr(files, "UPLOAD_DIR", tmp_path)
    monkeypatch.setattr(files, "create_file", create_file)
    monkeypatch.setattr(files, "list_files", lambda: list(records.values()))
    monkeypatch.setattr(files, "get_file", lambda file_id: records.get(file_id))
    monkeypatch.setattr(files, "delete_file", lambda file_id: records.pop(file_id, None) is not None)
    indexed: list[tuple[str, Path]] = []
    deleted_indexes: list[str] = []
    monkeypatch.setattr(
        files,
        "index_uploaded_file",
        lambda file_id, pdf_path: indexed.append((file_id, pdf_path)),
    )
    monkeypatch.setattr(files, "delete_retrieval_index", deleted_indexes.append)

    response = client.post(
        "/api/files/upload",
        files={"file": ("paper.pdf", b"%PDF-example", "application/pdf")},
    )

    assert response.status_code == 201
    uploaded = response.json()
    assert uploaded["filename"] == "paper.pdf"
    assert uploaded["size_bytes"] == len(b"%PDF-example")
    assert uploaded["status"] == "uploaded"
    file_id = uploaded["file_id"]
    assert (tmp_path / f"{file_id}.pdf").read_bytes() == b"%PDF-example"
    assert records[file_id]["filename"] == "paper.pdf"
    assert indexed == [(file_id, tmp_path / f"{file_id}.pdf")]

    listed = client.get("/api/files")
    assert listed.status_code == 200
    assert listed.json() == [records[file_id]]

    deleted = client.delete(f"/api/files/{file_id}")
    assert deleted.status_code == 204
    assert not (tmp_path / f"{file_id}.pdf").exists()
    assert deleted_indexes == [file_id]
    assert client.get("/api/files").json() == []


def test_delete_missing_file_returns_404(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(files, "UPLOAD_DIR", tmp_path)
    monkeypatch.setattr(files, "get_file", lambda file_id: None)

    response = client.delete("/api/files/missing")

    assert response.status_code == 404


def test_upload_rolls_back_file_and_metadata_when_milvus_indexing_fails(
    monkeypatch, tmp_path: Path
) -> None:
    records: dict[str, dict[str, object]] = {}
    monkeypatch.setattr(files, "UPLOAD_DIR", tmp_path)
    monkeypatch.setattr(
        files,
        "create_file",
        lambda file_id, filename, size_bytes: records.setdefault(
            file_id,
            {"file_id": file_id, "filename": filename, "size_bytes": size_bytes},
        ),
    )
    monkeypatch.setattr(files, "delete_file", lambda file_id: records.pop(file_id, None) is not None)
    deleted_indexes: list[str] = []
    monkeypatch.setattr(files, "delete_retrieval_index", deleted_indexes.append)
    monkeypatch.setattr(
        files,
        "index_uploaded_file",
        lambda file_id, pdf_path: (_ for _ in ()).throw(ConnectionError("Milvus offline")),
    )

    response = client.post(
        "/api/files/upload",
        files={"file": ("paper.pdf", b"%PDF-example", "application/pdf")},
    )

    assert response.status_code == 503
    assert response.json()["detail"] == "Milvus 索引失败，文件未保存"
    assert records == {}
    assert list(tmp_path.iterdir()) == []
    assert len(deleted_indexes) == 1
