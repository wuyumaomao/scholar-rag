from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda

from app.config import Settings
from app.documents.chunker import Chunk
from app.generation.answer_generator import AnswerGenerator
from app.generation.sources import build_sources
from app.main import app
from app.retrieval.retriever import RetrievalHit
from app.routers import chat, sessions


def test_source_numbering_matches_prompt_after_skipping_empty_evidence():
    hits = [
        RetrievalHit(Chunk("empty", "  ", {}), 0.9),
        RetrievalHit(Chunk("chunk-2", "Source text", {
            "page_nums": [3], "section_path": ["Methods"],
            "image_path": "private/local/path.png",
        }), 0.8),
    ]
    sources = build_sources(hits, "file-1", "paper.pdf")
    assert sources == [{
        "source_id": "S1", "file_id": "file-1", "filename": "paper.pdf",
        "chunk_id": "chunk-2", "page_nums": [3], "section_path": ["Methods"],
        "text": "Source text",
    }]
    seen = []

    def model(prompt):
        seen.append(prompt.to_messages()[1].content)
        return AIMessage(content="Answer [S1, p. 3]")

    generator = AnswerGenerator(
        settings=Settings(llm_enabled=True, llm_base_url="https://example.test/v1", llm_model="fake"),
        model=RunnableLambda(model),
    )
    generator.generate("Question", hits)
    assert "[S1] pages=3" in seen[0]
    assert "[S2]" not in seen[0]


def test_stream_sources_survive_history_and_are_scoped_to_each_message(monkeypatch):
    sources = build_sources([RetrievalHit(Chunk("chunk-1", "Evidence", {"page_nums": [2]}), 0.9)], "file-1", "paper.pdf")
    stored = []

    async def prepare(_request):
        return None, [object()], sources

    class Generator:
        async def astream(self, *_args):
            yield "Answer [S1, p. 2]"

    def save(session_id, role, content, *, sources=None):
        stored.append({"role": role, "content": content, "sources": sources or []})

    monkeypatch.setattr(chat, "_prepare_chat", prepare)
    monkeypatch.setattr(chat, "answer_generator", Generator())
    monkeypatch.setattr(chat, "create_session", lambda title: {"session_id": "session-1"})
    monkeypatch.setattr(chat, "add_message", save)
    monkeypatch.setattr(sessions, "get_session", lambda sid: {"session_id": sid})
    monkeypatch.setattr(sessions, "list_messages", lambda sid: stored)
    client = TestClient(app)
    result = client.post("/api/chat/stream", json={"file_id": "file-1", "query": "Question"})
    assert result.status_code == 200
    assert result.text.index("event: sources") < result.text.index("event: token")
    history = client.get("/api/sessions/session-1/history").json()
    assert history[0]["sources"] == []
    assert history[1]["sources"] == sources
    assert history[1]["content"] == "Answer [S1, p. 2]"
