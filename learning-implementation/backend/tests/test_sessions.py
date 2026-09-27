"""会话 API 的行为测试。"""

from fastapi.testclient import TestClient

from app.main import app
from app.routers import chat, sessions


client = TestClient(app)


def test_session_metadata_and_deletion_lifecycle(monkeypatch) -> None:
    """首条提问命名会话，删除后元数据和历史都不可访问。"""
    records: dict[str, dict[str, object]] = {}
    messages: dict[str, list[dict[str, str]]] = {}
    timestamps = iter([100.0, 200.0])

    def create_session(title: str = "") -> dict[str, object]:
        session = {
            "session_id": "session-1",
            "title": title,
            "created_at": 100.0,
            "updated_at": next(timestamps),
        }
        records[session["session_id"]] = session
        messages[session["session_id"]] = []
        return session

    def get_session(session_id: str) -> dict[str, object] | None:
        return records.get(session_id)

    def touch_session(session_id: str) -> None:
        records[session_id]["updated_at"] = next(timestamps)

    def add_message(session_id: str, role: str, content: str) -> None:
        messages[session_id].append({"role": role, "content": content})

    def list_messages(session_id: str) -> list[dict[str, str]]:
        return messages[session_id]

    def delete_session(session_id: str) -> bool:
        if session_id not in records:
            return False
        records.pop(session_id)
        messages.pop(session_id)
        return True

    monkeypatch.setattr(chat, "create_session", create_session)
    monkeypatch.setattr(chat, "get_session", get_session)
    monkeypatch.setattr(chat, "touch_session", touch_session)
    monkeypatch.setattr(chat, "add_message", add_message)
    monkeypatch.setattr(sessions, "get_session", get_session)
    monkeypatch.setattr(sessions, "list_messages", list_messages)
    monkeypatch.setattr(sessions, "delete_session", delete_session)
    monkeypatch.setattr(sessions, "list_sessions", lambda: list(records.values()))

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
