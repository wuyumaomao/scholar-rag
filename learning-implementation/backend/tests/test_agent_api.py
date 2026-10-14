from fastapi.testclient import TestClient

from app.main import app
from app.agent.paper_agent import AgentExecutionError
from app.routers import agent
from app.agent.paper_agent import AgentConversationError


def setup_file(monkeypatch, tmp_path):
    (tmp_path / "paper.pdf").write_bytes(b"pdf")
    monkeypatch.setattr(agent.retrieval_api, "UPLOAD_DIR", tmp_path)
    monkeypatch.setattr(agent.retrieval_api, "get_file", lambda _: {"file_id": "paper"})


def test_agent_api_returns_single_task_result(monkeypatch, tmp_path):
    setup_file(monkeypatch, tmp_path)

    class FakeAgent:
        def __init__(self, **kwargs):
            pass

        async def run(self, **kwargs):
            assert kwargs["file_id"] == "paper"
            assert kwargs["pdf_path"] == tmp_path / "paper.pdf"
            return {"answer": "Answer", "status": "completed", "tool_calls_used": 1,
                    "sources": [], "trace": []}

    monkeypatch.setattr(agent, "PaperWorkflow", FakeAgent)
    response = TestClient(app).post("/api/agent", json={"file_id": "paper", "query": "Question"})
    assert response.status_code == 200
    assert response.json()["status"] == "completed"


def test_agent_api_rejects_unknown_fields_and_blank_input():
    client = TestClient(app)
    for payload in [{"file_id": "paper", "query": " "},
                    {"file_id": "paper", "query": "q", "session_id": "session"}]:
        assert client.post("/api/agent", json=payload).status_code == 422


def test_agent_api_missing_file_is_404(monkeypatch, tmp_path):
    monkeypatch.setattr(agent.retrieval_api, "get_file", lambda _: None)
    client = TestClient(app)
    payload = {"file_id": "paper", "query": "question"}
    assert client.post("/api/agent", json=payload).status_code == 404
    monkeypatch.setattr(agent.retrieval_api, "get_file", lambda _: {"file_id": "paper"})
    monkeypatch.setattr(agent.retrieval_api, "UPLOAD_DIR", tmp_path)
    assert client.post("/api/agent", json=payload).status_code == 404


def test_agent_api_model_failure_is_sanitized_503(monkeypatch, tmp_path):
    setup_file(monkeypatch, tmp_path)

    class FailingAgent:
        def __init__(self, **kwargs):
            pass

        async def run(self, **kwargs):
            raise AgentExecutionError("private-provider-secret")

    monkeypatch.setattr(agent, "PaperWorkflow", FailingAgent)
    response = TestClient(app).post("/api/agent", json={"file_id": "paper", "query": "question"})
    assert response.status_code == 503
    assert "private" not in response.text


def test_agent_api_passes_thread_and_maps_conflicts(monkeypatch, tmp_path):
    setup_file(monkeypatch, tmp_path)

    class ConflictAgent:
        def __init__(self, **kwargs):
            assert kwargs["checkpointer"] is agent.checkpointer
            assert kwargs["conversation_locks"] is agent.conversation_locks

        async def run(self, **kwargs):
            assert kwargs["thread_id"] == "thread-1"
            raise AgentConversationError("会话已绑定另一篇论文，请创建新会话")

    monkeypatch.setattr(agent, "PaperWorkflow", ConflictAgent)
    response = TestClient(app).post("/api/agent", json={
        "file_id": "paper", "query": "question", "thread_id": "thread-1"})
    assert response.status_code == 409
    assert TestClient(app).post("/api/agent", json={
        "file_id": "paper", "query": "question", "thread_id": " "}).status_code == 422
