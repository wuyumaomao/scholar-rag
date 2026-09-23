"""内存会话存储。"""

from uuid import uuid4

sessions: dict[str, dict[str, object]] = {}


def create_session() -> dict[str, object]:
    session_id = str(uuid4())
    session = {
        "session_id": session_id,
        "title": "",
        "messages": [],
    }
    sessions[session_id] = session
    return session


def list_sessions() -> list[dict[str, object]]:
    return [
        {
            "session_id": session["session_id"],
            "title": session["title"],
        }
        for session in sessions.values()
    ]


def get_session(session_id: str) -> dict[str, object] | None:
    return sessions.get(session_id)
