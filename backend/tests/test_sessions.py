"""会话 API 的行为测试。"""

from types import SimpleNamespace

from fastapi.testclient import TestClient

from app import store
from app.main import app


client = TestClient(app)


def setup_function() -> None:
    """让每个测试从空的内存存储开始。"""
    store.sessions.clear()


def test_session_metadata_and_deletion_lifecycle(monkeypatch) -> None:
    """首条提问命名会话，删除后元数据和历史都不可访问。"""
    timestamps = iter([100.0, 200.0])
    monkeypatch.setattr(store, "time", SimpleNamespace(time=lambda: next(timestamps)))
    query = "a" * 51
    created = client.post("/api/chat", json={"query": query})

    assert created.status_code == 200
    session_id = created.json()["session_id"]

    detail = client.get(f"/api/sessions/{session_id}")
    assert detail.status_code == 200
    assert detail.json()["title"] == query[:50]
    assert detail.json()["created_at"] == 100.0
    assert detail.json()["updated_at"] == 100.0

    second_chat = client.post(
        "/api/chat", json={"query": "第二个问题", "session_id": session_id}
    )
    assert second_chat.status_code == 200
    refreshed_detail = client.get(f"/api/sessions/{session_id}")
    assert refreshed_detail.json()["title"] == query[:50]
    assert refreshed_detail.json()["updated_at"] == 200.0

    deleted = client.delete(f"/api/sessions/{session_id}")
    assert deleted.status_code == 204
    assert client.get(f"/api/sessions/{session_id}").status_code == 404
    assert client.get(f"/api/sessions/{session_id}/history").status_code == 404
    assert session_id not in [
        session["session_id"] for session in client.get("/api/sessions").json()
    ]
