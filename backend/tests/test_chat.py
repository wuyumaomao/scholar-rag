from pathlib import Path

import pytest
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


def test_stream_chat_emits_tokens_then_done_and_persists_complete_answer(
    monkeypatch, tmp_path: Path
) -> None:
    (tmp_path / "file-1.pdf").write_bytes(b"pdf")
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

    class StreamingAnswerGenerator:
        async def astream(self, query, hits):
            assert query == "Explain the result."
            assert hits == [hit]
            yield "The method "
            yield "works."

    monkeypatch.setattr(chat, "retrieval_api", RetrievalApi, raising=False)
    monkeypatch.setattr(chat, "answer_generator", StreamingAnswerGenerator(), raising=False)
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
        lambda session_id, role, content: saved_messages.append(
            (session_id, role, content)
        ),
    )

    response = TestClient(app).post(
        "/api/chat/stream",
        json={"file_id": "file-1", "query": "Explain the result."},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    frames = response.text.strip().split("\n\n")
    assert frames == [
        'event: token\ndata: {"text": "The method "}',
        'event: token\ndata: {"text": "works."}',
        'event: done\ndata: {"session_id": "session-1"}',
    ]
    assert saved_messages == [
        ("session-1", "user", "Explain the result."),
        ("session-1", "assistant", "The method works."),
    ]


def test_stream_chat_without_hits_streams_deterministic_answer(
    monkeypatch, tmp_path: Path
) -> None:
    (tmp_path / "file-1.pdf").write_bytes(b"pdf")
    saved_messages: list[tuple[str, str, str]] = []

    class RetrievalService:
        def retrieve(self, *_args, **_kwargs):
            return []

    class RetrievalApi:
        UPLOAD_DIR = tmp_path
        FIGURE_DIR = tmp_path / "figures"
        settings = type("Settings", (), {"top_k": 5, "fetch_k": 20, "min_score": 0.8})()
        retrieval_service = RetrievalService()
        get_file = staticmethod(lambda file_id: {"file_id": file_id})

    class UnusedAnswerGenerator:
        async def astream(self, *_args, **_kwargs):
            raise AssertionError("the model must not run without retrieved evidence")
            yield "unreachable"

    monkeypatch.setattr(chat, "retrieval_api", RetrievalApi, raising=False)
    monkeypatch.setattr(chat, "answer_generator", UnusedAnswerGenerator(), raising=False)
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
        lambda session_id, role, content: saved_messages.append(
            (session_id, role, content)
        ),
    )

    response = TestClient(app).post(
        "/api/chat/stream",
        json={"file_id": "file-1", "query": "Question?"},
    )

    expected = "我没有在这篇论文中检索到足够证据来回答这个问题。"
    assert response.status_code == 200
    assert f'event: token\ndata: {{"text": "{expected}"}}' in response.text
    assert 'event: done\ndata: {"session_id": "session-1"}' in response.text
    assert saved_messages[-1] == ("session-1", "assistant", expected)


def test_stream_chat_reports_generation_error_without_persisting_partial_answer(
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
        async def astream(self, *_args, **_kwargs):
            yield "partial answer"
            raise AnswerGenerationError("upstream unavailable")

    monkeypatch.setattr(chat, "retrieval_api", RetrievalApi, raising=False)
    monkeypatch.setattr(chat, "answer_generator", FailingAnswerGenerator(), raising=False)
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
        "/api/chat/stream",
        json={"file_id": "file-1", "query": "Question?"},
    )

    assert response.status_code == 200
    assert 'event: token\ndata: {"text": "partial answer"}' in response.text
    assert 'event: error\ndata: {"detail": "回答生成服务当前不可用"}' in response.text
    assert "event: done" not in response.text
    assert "Answer generation failed: upstream unavailable" in caplog.text
    assert created_sessions == []
    assert saved_messages == []


@pytest.mark.parametrize(
    ("file_exists", "session_exists", "expected_detail"),
    [
        (False, True, "文件不存在"),
        (True, False, "会话不存在"),
    ],
)
def test_stream_chat_validation_errors_remain_http_json_before_streaming(
    monkeypatch,
    tmp_path: Path,
    file_exists: bool,
    session_exists: bool,
    expected_detail: str,
) -> None:
    if file_exists:
        (tmp_path / "file-1.pdf").write_bytes(b"pdf")

    class RetrievalApi:
        UPLOAD_DIR = tmp_path
        FIGURE_DIR = tmp_path / "figures"
        settings = type("Settings", (), {"top_k": 5, "fetch_k": 20, "min_score": 0.8})()
        get_file = staticmethod(
            lambda file_id: {"file_id": file_id} if file_exists else None
        )

    monkeypatch.setattr(chat, "retrieval_api", RetrievalApi, raising=False)
    monkeypatch.setattr(
        chat,
        "get_session",
        lambda _session_id: {"session_id": "session-1"} if session_exists else None,
    )

    response = TestClient(app).post(
        "/api/chat/stream",
        json={
            "file_id": "file-1",
            "query": "Question?",
            "session_id": "session-1",
        },
    )

    assert response.status_code == 404
    assert response.json() == {"detail": expected_detail}
    assert not response.headers["content-type"].startswith("text/event-stream")
