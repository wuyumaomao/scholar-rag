from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from app.generation.answer_generator import AnswerGenerationError
from app.retrieval.retriever import RetrievalHit
from app.documents.chunker import Chunk
from app.routers import chat


def test_chat_retrieves_evidence_generates_answer_and_persists_messages(
    monkeypatch, tmp_path: Path
) -> None:
    pdf_path = tmp_path / "file-1.pdf"
    pdf_path.write_bytes(b"pdf")
    messages: list[tuple[str, str, str]] = []
    retrieved: dict[str, object] = {}
    hit = RetrievalHit(
        chunk=Chunk(
            chunk_id="element-000001-parent",
            context="The paper estimates depth with a CNN-CRF.",
            meta={"page_nums": [1]},
        ),
        score=0.9,
    )

    class RetrievalService:
        def retrieve(self, *args, **kwargs):
            retrieved["args"] = args
            retrieved["kwargs"] = kwargs
            return [hit]

    class AnswerGenerator:
        def generate(self, query, hits):
            assert query == "How is depth estimated?"
            assert hits == [hit]
            return "The paper uses a CNN-CRF [S1, p. 1]."

    class RetrievalApi:
        UPLOAD_DIR = tmp_path
        FIGURE_DIR = tmp_path / "figures"
        settings = type("Settings", (), {"top_k": 5, "fetch_k": 20, "min_score": 0.8})()
        retrieval_service = RetrievalService()
        get_file = staticmethod(lambda file_id: {"file_id": file_id})

    monkeypatch.setattr(chat, "retrieval_api", RetrievalApi, raising=False)
    monkeypatch.setattr(chat, "answer_generator", AnswerGenerator(), raising=False)
    monkeypatch.setattr(
        chat,
        "create_session",
        lambda title: {"session_id": "session-1", "title": title},
    )
    monkeypatch.setattr(chat, "get_session", lambda _session_id: None)
    monkeypatch.setattr(chat, "touch_session", lambda _session_id: None)
    monkeypatch.setattr(
        chat,
        "add_message",
        lambda session_id, role, content: messages.append((session_id, role, content)),
    )

    response = TestClient(app).post(
        "/api/chat",
        json={"file_id": "file-1", "query": "How is depth estimated?"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "answer": "The paper uses a CNN-CRF [S1, p. 1].",
        "session_id": "session-1",
    }
    assert retrieved["args"] == (
        "file-1",
        pdf_path,
        "How is depth estimated?",
        tmp_path / "figures" / "file-1",
    )
    assert retrieved["kwargs"] == {"top_k": 5, "child_top_k": 20, "min_score": 0.8}
    assert messages == [
        ("session-1", "user", "How is depth estimated?"),
        ("session-1", "assistant", "The paper uses a CNN-CRF [S1, p. 1]."),
    ]


def test_chat_does_not_persist_messages_when_answer_generation_fails(
    monkeypatch, tmp_path: Path, caplog
) -> None:
    (tmp_path / "file-1.pdf").write_bytes(b"pdf")
    created_sessions: list[str] = []
    saved_messages: list[tuple[str, str, str]] = []
    hit = RetrievalHit(
        chunk=Chunk(
            chunk_id="element-000001-parent",
            context="Evidence.",
            meta={"page_nums": [1]},
        ),
        score=0.9,
    )

    class RetrievalService:
        def retrieve(self, *_args, **_kwargs):
            return [hit]

    class RetrievalApi:
        UPLOAD_DIR = tmp_path
        FIGURE_DIR = tmp_path / "figures"
        settings = type("Settings", (), {"top_k": 5, "fetch_k": 20, "min_score": 0.8})()
        retrieval_service = RetrievalService()
        get_file = staticmethod(lambda file_id: {"file_id": file_id})

    class FailingAnswerGenerator:
        def generate(self, *_args, **_kwargs):
            raise AnswerGenerationError("upstream unavailable")

    monkeypatch.setattr(chat, "retrieval_api", RetrievalApi, raising=False)
    monkeypatch.setattr(
        chat, "answer_generator", FailingAnswerGenerator(), raising=False
    )
    monkeypatch.setattr(
        chat,
        "create_session",
        lambda title: created_sessions.append(title),
    )
    monkeypatch.setattr(chat, "get_session", lambda _session_id: None)
    monkeypatch.setattr(chat, "touch_session", lambda _session_id: None)
    monkeypatch.setattr(
        chat,
        "add_message",
        lambda session_id, role, content: saved_messages.append(
            (session_id, role, content)
        ),
    )

    response = TestClient(app).post(
        "/api/chat",
        json={"file_id": "file-1", "query": "Explain the result."},
    )

    assert response.status_code == 503
    assert response.json()["detail"] == "回答生成服务当前不可用"
    assert "Answer generation failed: upstream unavailable" in caplog.text
    assert created_sessions == []
    assert saved_messages == []
