from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from app.pdf_parser import ParsedElement, ParsedPdf
from app.routers import retrieval
from app.retrieval_service import RetrievalService


class FakeEmbedder:
    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [[1.0, 0.0] for _ in texts]

    def embed_query(self, query: str) -> list[float]:
        return [1.0, 0.0]


def test_retrieve_endpoint_returns_parent_results_for_uploaded_pdf(
    monkeypatch, tmp_path: Path
) -> None:
    pdf_path = tmp_path / "file-1.pdf"
    pdf_path.write_bytes(b"pdf")
    monkeypatch.setattr(retrieval, "UPLOAD_DIR", tmp_path)
    monkeypatch.setattr(
        retrieval,
        "get_file",
        lambda file_id: {"file_id": file_id} if file_id == "file-1" else None,
    )
    monkeypatch.setattr(
        retrieval,
        "retrieval_service",
        RetrievalService(
            embedder=FakeEmbedder(),
            parser=lambda path, *, figure_dir: ParsedPdf(
                page_count=1,
                elements=[
                    ParsedElement(
                        element_id="element-000001",
                        element_type="paragraph",
                        docling_type="TextItem",
                        docling_label="text",
                        text="A useful result.",
                        page_num=1,
                        order=1,
                        bbox=None,
                    )
                ],
            ),
        ),
    )

    response = TestClient(app).post(
        "/api/retrieve",
        json={"file_id": "file-1", "query": "Find useful information", "top_k": 2},
    )

    assert response.status_code == 200
    assert response.json() == {
        "results": [
            {
                "chunk_id": "element-000001-parent",
                "score": 1.0,
                "context": "A useful result.",
                "metadata": {
                    "source_element_ids": ["element-000001"],
                    "element_types": ["paragraph"],
                    "page_nums": [1],
                    "section_path": [],
                    "related_element_ids": [],
                    "orders": [1],
                    "provenance": [],
                    "image_path": "",
                },
            }
        ]
    }


def test_retrieve_endpoint_returns_404_for_unknown_file(monkeypatch) -> None:
    monkeypatch.setattr(retrieval, "get_file", lambda _file_id: None)

    response = TestClient(app).post(
        "/api/retrieve", json={"file_id": "missing", "query": "question"}
    )

    assert response.status_code == 404


def test_retrieve_endpoint_returns_404_when_uploaded_pdf_is_missing(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(retrieval, "UPLOAD_DIR", tmp_path)
    monkeypatch.setattr(retrieval, "get_file", lambda file_id: {"file_id": file_id})

    response = TestClient(app).post(
        "/api/retrieve", json={"file_id": "file-1", "query": "question"}
    )

    assert response.status_code == 404


def test_retrieve_endpoint_rejects_blank_query() -> None:
    response = TestClient(app).post(
        "/api/retrieve", json={"file_id": "file-1", "query": "   "}
    )

    assert response.status_code == 422
