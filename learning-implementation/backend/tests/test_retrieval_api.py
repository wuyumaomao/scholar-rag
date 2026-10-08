from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.pdf_parser import ParsedElement, ParsedPdf
from app.routers import retrieval
from app.retrieval_service import RetrievalService
from app.routers.retrieval import RetrieveRequest


class FakeEmbedder:
    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [[1.0, 0.0] for _ in texts]

    def embed_query(self, query: str) -> list[float]:
        return [1.0, 0.0]


def test_retrieve_request_uses_similarity_threshold_default() -> None:
    request = RetrieveRequest(file_id="file-1", query="question")

    assert request.min_score == 0.8
    assert request.use_hyde is False


def test_retrieve_request_accepts_metadata_filters() -> None:
    request = RetrieveRequest(
        file_id="file-1",
        query="question",
        filters={
            "element_types": ["figure", "table"],
            "page_from": 2,
            "page_to": 4,
            "section_path_prefix": ["Methods"],
        },
    )

    assert request.filters.page_from == 2
    assert request.filters.element_types == ["figure", "table"]


def test_retrieve_request_rejects_invalid_metadata_filters() -> None:
    with pytest.raises(ValueError, match="page"):
        RetrieveRequest(
            file_id="file-1",
            query="question",
            filters={"page_from": 5, "page_to": 2},
        )


def test_retrieve_endpoint_passes_hyde_flag_to_service(monkeypatch, tmp_path: Path) -> None:
    pdf_path = tmp_path / "file-1.pdf"
    pdf_path.write_bytes(b"pdf")
    monkeypatch.setattr(retrieval, "UPLOAD_DIR", tmp_path)
    monkeypatch.setattr(retrieval, "get_file", lambda _file_id: {"file_id": "file-1"})
    captured: dict[str, object] = {}

    class Service:
        def retrieve(self, *args, **kwargs):
            captured.update(kwargs)
            return []

    monkeypatch.setattr(retrieval, "retrieval_service", Service())
    response = TestClient(app).post(
        "/api/retrieve",
        json={"file_id": "file-1", "query": "question", "use_hyde": True},
    )

    assert response.status_code == 200
    assert captured["use_hyde"] is True


def test_retrieve_endpoint_passes_metadata_filters_to_service(monkeypatch, tmp_path: Path) -> None:
    pdf_path = tmp_path / "file-1.pdf"
    pdf_path.write_bytes(b"pdf")
    monkeypatch.setattr(retrieval, "UPLOAD_DIR", tmp_path)
    monkeypatch.setattr(retrieval, "get_file", lambda _file_id: {"file_id": "file-1"})
    captured: dict[str, object] = {}

    class Service:
        def retrieve(self, *args, **kwargs):
            captured.update(kwargs)
            return []

    monkeypatch.setattr(retrieval, "retrieval_service", Service())
    response = TestClient(app).post(
        "/api/retrieve",
        json={
            "file_id": "file-1",
            "query": "question",
            "filters": {"element_types": ["figure"], "page_from": 2},
        },
    )

    assert response.status_code == 200
    assert captured["filters"].element_types == ("figure",)
    assert captured["filters"].page_from == 2


def test_retrieve_endpoint_returns_clear_error_when_hyde_is_unconfigured(
    monkeypatch, tmp_path: Path
) -> None:
    pdf_path = tmp_path / "file-1.pdf"
    pdf_path.write_bytes(b"pdf")
    monkeypatch.setattr(retrieval, "UPLOAD_DIR", tmp_path)
    monkeypatch.setattr(retrieval, "get_file", lambda _file_id: {"file_id": "file-1"})
    monkeypatch.setattr(
        retrieval,
        "retrieval_service",
        RetrievalService(
            embedder=FakeEmbedder(),
            parser=lambda path, *, figure_dir: ParsedPdf(page_count=1, elements=[]),
        ),
    )

    response = TestClient(app).post(
        "/api/retrieve",
        json={"file_id": "file-1", "query": "question", "use_hyde": True},
    )

    assert response.status_code == 422
    assert "LLM_ENABLED=true" in response.json()["detail"]


def test_retrieve_request_uses_shared_settings_defaults() -> None:
    request = RetrieveRequest(file_id="file-1", query="question")

    assert request.top_k == retrieval.settings.top_k
    assert request.child_top_k == retrieval.settings.fetch_k
    assert request.min_score == retrieval.settings.min_score


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
    results = response.json()["results"]
    assert len(results) == 1
    assert results[0] == {
        "chunk_id": "element-000001-parent",
        "score": pytest.approx((1 + 1.25) / 61),
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
